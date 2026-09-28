import logging

import flet as ft

from torforum.ui.app import main

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    ft.run(main)
