"""Choose the terminal or graphical interface for rolldown."""


# Set currently available
sets = ['4.5', '5.5', '6', '7']


if __name__ == '__main__':
    # Get set from user
    A = -1
    while not 0 < A <= len(sets):
        print('Which set would you like to rolldown on?')
        for idx, tft_set in enumerate(sets):
            print(f'[{idx + 1}] {tft_set}')

        try:
            A = int(input())
            cur_set = f'TFT_Set_{sets[A - 1]}'
            break
        except (TypeError, ValueError, IndexError):
            continue

    # Get interface mode from user
    A = -1
    while A not in (1, 2):
        print('Would you like to use the terminal or the graphical interface?')
        A = input('Type 1 for terminal or 2 for graphical.\n')

        if A == '1':
            from rolldown import main
            main(cur_set)
        elif A == '2':
            from user_interface import main
            main(cur_set)
        else:
            continue
