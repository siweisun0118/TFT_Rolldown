"""Choose the terminal or graphical interface for rolldown."""


import sys


# Current sets available
sets = ['4.5', '5.5', '6', '7']


if __name__ == '__main__':
    # Get set from user
    answer = -1
    while not 0 < answer <= len(sets):
        print('Which set would you like to rolldown on?')
        for idx, tft_set in enumerate(sets):
            print(f'[{idx + 1}] {tft_set}')

        try:
            answer = int(input())
            cur_set = f'TFT_Set_{sets[answer - 1]}'
            break
        except (TypeError, ValueError):
            continue


    # Get interface mode from user
    answer = -1
    while answer != 1 and answer != -2:
        print('Would you like to use the terminal or the graphical interface?')
        answer = input('Type 1 for terminal or 2 for graphical.\n')

        if answer == '1':
            from rolldown import main
            main(cur_set)
        elif answer == '2':
            from user_interface import main
            main(cur_set)
        else:
            continue
