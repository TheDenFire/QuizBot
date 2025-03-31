from aiogram.fsm.state import StatesGroup, State

class QuestStates(StatesGroup):
    CONFIRM_RESET = State()
    TASK9_TEXT = State()
    CITY_INPUT = State()
    TASK1_PHOTO = State()
    TASK2_PHOTO = State()  # <-- Добавлено
    TASK2_TEXT = State()  # <-- Добавлено
    TASK3_PHOTO = State()
    TASK4_TEXT = State()
    TASK4_PHOTO = State()
    TASK5_PHOTO = State()
    TASK6_ANSWER = State()
    TASK7_TEXT = State()
    TASK7_ANSWER = State()
    TASK8_ANSWER = State()
    TASK8_PHOTO = State()
    TASK9_PHOTO = State()
    TASK10_REPORT = State()
    TASK11_PHOTO = State()
    MENU = State()  # Новое состояние для выхода