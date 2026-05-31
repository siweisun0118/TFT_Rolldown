"""Tests for the performance and server-robustness improvements."""

# Standard libraries
import io
import socket
import struct
import threading

import pytest


# ----------------------------------------------------------- perf §1.1 / 1.11
def test_pool_cache_is_used_after_first_fetch(monkeypatch, game):
    """The offline path treats the local pool as authoritative.

    For the on-line path we exercise the cache invalidation API and confirm
    the dirty flag flips correctly.
    """
    # Simulate an online game by toggling offline=False on a fresh instance.
    game.offline = False
    game._pool_cache = {1: {'Aatrox': 5}, 2: {}, 3: {}, 4: {}, 5: {}}
    game._pool_dirty = False
    pool = game.build_champion_pool()
    # 5 Aatrox should be materialised.
    assert sum(1 for u in pool[1] if u.name == 'Aatrox') == 5
    # Adjust cache via the helper used by buy/sell paths.
    game._adjust_cache(game.champions_dict['Aatrox'], -1)
    pool2 = game.build_champion_pool()
    assert sum(1 for u in pool2[1] if u.name == 'Aatrox') == 4
    # Invalidate – next build should re-fetch (we monkey-patch send_message).
    fetched = {'flag': False}
    def _fake_send(_sock, _msg):
        fetched['flag'] = True
        return '{}'  # empty pool
    from shared import game as game_mod
    monkeypatch.setattr(game_mod, 'send_message', _fake_send)
    game.invalidate_pool_cache()
    game.build_champion_pool()
    assert fetched['flag']


def test_three_starred_is_per_instance(set_dir):
    """Perf §1.11: each Game has its own THREE_STARRED tracker."""
    from shared.game import Game
    g1 = Game(set_dir, gold=100, level=3, offline=True)
    g2 = Game(set_dir, gold=100, level=3, offline=True)
    g1.three_starred.add('Aatrox')
    assert 'Aatrox' not in g2.three_starred


# ----------------------------------------------------------- perf §1.9
def test_splash_paths_are_cached_at_startup(game):
    """Splash paths should resolve without touching the filesystem after init."""
    cache = game._splash_paths
    assert 'Aatrox' in cache
    aatrox_path = game.splash_path(game.champions_dict['Aatrox'])
    assert aatrox_path is not None
    assert aatrox_path.exists()


# ----------------------------------------------------------- framing helpers (§2.2)
def test_framing_round_trip():
    """Length-prefixed messages survive a back-to-back round trip."""
    from shared.networking_client import send_framed as client_send, recv_framed as client_recv
    from shared.networking_server import send_framed as server_send, recv_framed as server_recv

    # Use a socketpair to avoid hitting the network stack.
    a, b = socket.socketpair()
    try:
        client_send(a, 'hello world')
        assert server_recv(b) == 'hello world'

        server_send(b, 'large message ' * 1000)
        assert client_recv(a) == 'large message ' * 1000
    finally:
        a.close()
        b.close()


def test_framing_handles_partial_recv():
    """If the OS hands us fewer bytes than the message length, we keep reading."""
    from shared.networking_client import recv_framed
    a, b = socket.socketpair()
    try:
        payload = b'hello, partial recv!'
        header = struct.pack('!I', len(payload))
        # Split the send into deliberately tiny chunks.
        b.sendall(header[:1])
        b.sendall(header[1:])
        b.sendall(payload[:5])
        b.sendall(payload[5:])
        assert recv_framed(a) == payload.decode()
    finally:
        a.close()
        b.close()


# ----------------------------------------------------------- transactional acks (§2.9)
def test_server_returns_ok_for_buy_and_sell(monkeypatch, tmp_path, set_dir):
    """The server should respond with ``OK:`` on successful buy/sell."""
    from shared.networking_server import (
        buy_champion, sell_champion, populate_champ_pool,
        SERVER_TRANSITIONS_LOG,
    )
    from shared.rolldown_enums import POOL_LOCK, SERVER_TRANSITIONS_LOG as LOG_PATH
    # Redirect the transition log into the tmp dir.
    monkeypatch.setattr('shared.networking_server.SERVER_TRANSITIONS_LOG',
                        tmp_path / 'log.jsonl')

    with POOL_LOCK:
        champs, _ = populate_champ_pool(set_dir)
        response_buy = buy_champion('buy: Aatrox', champs)
        assert response_buy.startswith('OK')
        response_sell = sell_champion('sell: Aatrox: 1', champs)
        assert response_sell.startswith('OK')


def test_server_returns_error_for_unknown_champion(monkeypatch, tmp_path, set_dir):
    """Server improvement §2.5 + §2.9: unknown champion → structured error."""
    from shared.networking_server import (
        buy_champion, populate_champ_pool, UnknownChampionError,
    )
    from shared.rolldown_enums import POOL_LOCK
    monkeypatch.setattr('shared.networking_server.SERVER_TRANSITIONS_LOG',
                        tmp_path / 'log.jsonl')

    with POOL_LOCK:
        champs, _ = populate_champ_pool(set_dir)
        with pytest.raises(UnknownChampionError):
            buy_champion('buy: NotAUnit', champs)


# ----------------------------------------------------------- transition log (§2.12)
def test_transition_log_persists_buy_and_sell(monkeypatch, tmp_path, set_dir):
    """Every successful operation should append a record to the log."""
    log_path = tmp_path / 'log.jsonl'
    monkeypatch.setattr('shared.networking_server.SERVER_TRANSITIONS_LOG', log_path)

    from shared.networking_server import (
        buy_champion, sell_champion, populate_champ_pool, _replay_transitions,
    )
    from shared.rolldown_enums import POOL_LOCK

    with POOL_LOCK:
        champs, _ = populate_champ_pool(set_dir)
        buy_champion('buy: Aatrox', champs)
        sell_champion('sell: Aatrox: 1', champs)

    assert log_path.exists()
    lines = log_path.read_text(encoding='utf-8').splitlines()
    assert len(lines) >= 2
    import json
    record = json.loads(lines[0])
    assert record['op'] == 'buy' and record['unit'] == 'Aatrox'
    record2 = json.loads(lines[1])
    assert record2['op'] == 'sell' and record2['unit'] == 'Aatrox'

    # Replaying the log should reproduce the pool state.
    with POOL_LOCK:
        champs2, _ = populate_champ_pool(set_dir)
        _replay_transitions(champs2)
    # Pool state is internal; we just check the helper does not raise.
