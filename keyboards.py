import types

from aiogram.utils.keyboard import ReplyKeyboardBuilder

def main_menu_kb():
    builder = ReplyKeyboardBuilder()
    buttons = [
        "🛰 Космическая карта",
        "🌍 Экологические данные",
        "📰 Новости",
        "🗺️ Квест-трип по городу",
        "🎓 Викторина о космосе",
        "🏅 Профиль"
    ]
    for btn in buttons:
        builder.add(types.KeyboardButton(text=btn))
    builder.adjust(2, 2, 2)
    return builder.as_markup(resize_keyboard=True)