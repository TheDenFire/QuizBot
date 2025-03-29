import logging
import os
import urllib

import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command, or_f
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Данные подключения к PostgreSQL
POSTGRES_URI = os.getenv("POSTGRESURL")
DB_USER = os.getenv("DATABASE_USER")
DB_PASSWORD = os.getenv("DATABASE_PASSWORD")

# Инициализация бота
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

class SurveyStates(StatesGroup):
    QUESTION = State()


async def get_db():
    try:
        conn = await asyncpg.connect(
            dsn=POSTGRES_URI,
            user=DB_USER,
            password=DB_PASSWORD,
            timeout=10  # Установите таймаут 10 секунд
        )
        print("Успешное подключение к PostgreSQL!")
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения: {e}")
        raise

# Создаем клавиатуру главного меню
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


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or ""

    conn = await get_db()
    try:
        await conn.execute(
            "INSERT INTO users (id, username) VALUES ($1, $2) "
            "ON CONFLICT (id) DO NOTHING",
            user_id, username
        )
    finally:
        await conn.close()

    welcome_text = (
        "🚀 Привет, космический путешественник! 🚀\n\n"
        "Добро пожаловать в чат-бот SR space, твой личный космический центр управления!\n\n"
        "Меня зовут Спэйси! От лица всей команды рад приветствовать! Я здесь, чтобы сделать космос ближе для тебя.\n"
        "🔹 /map — Космическая карта спутников 🛰\n"
        "🔹 /news — Свежие новости о космосе 📰\n"
        "🔹 /eco — Данные о загрязнении и климате 🌍\n"
        "🔹 /quest — Космический квест-трип по твоему городу 🗺️\n"
        "🔹 /quiz — Викторина о космосе 🎓\n"
        "🔹 /profile — Твой личный профиль 🏅"
    )

    await message.answer(welcome_text)
    await message.answer(
        "Выбери команду или нажми на кнопку ниже ⬇️",
        reply_markup=main_menu_kb()
    )
    await state.clear()


@dp.message(or_f(F.text == "🏅 Профиль", Command("profile")))
async def show_profile(message: types.Message):
    await show_user_profile(message.from_user.id, message)


async def show_user_profile(user_id: int, message: types.Message):
    conn = await get_db()
    try:
        user = await conn.fetchrow(
            "SELECT username, points FROM users WHERE id = $1",
            user_id
        )
    except Exception as e:
        logger.error(f"Database error: {e}")
        await message.answer("Ошибка при получении профиля")
        return
    finally:
        await conn.close()

    if not user:
        await message.answer("Профиль не найден!")
        return

    # Создаем клавиатуру профиля
    builder = InlineKeyboardBuilder()
    builder.button(text="🏆 Топ-5 рейтинг", callback_data="show_rating")

    profile_text = (
        f"👤 Ваш профиль:\n"
        f"▫️ Имя: {user['username'] or 'гость'}\n"
        f"▫️ Баллы: {user['points']}"
    )

    await message.answer(
        profile_text,
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "show_rating")
async def show_rating(callback: types.CallbackQuery):
    try:
        conn = await get_db()
        top_users = await conn.fetch(
            "SELECT username, points FROM users ORDER BY points DESC LIMIT 5"
        )
    except Exception as e:
        logger.error(f"Rating error: {e}")
        await callback.answer("⚠️ Ошибка загрузки рейтинга")
        return
    finally:
        await conn.close()

    if not top_users:
        await callback.message.answer("🏆 Рейтинг пока пуст!")
        return

    rating_text = "🏆 Топ-5 пользователей:\n\n"
    for i, user in enumerate(top_users, 1):
        username = user['username'] or "Аноним"
        rating_text += f"{i}. {username} - ⭐ {user['points']} баллов\n"

    # Добавляем отправку сообщения
    await callback.message.answer(rating_text)
    await callback.answer()

# Обработчики для других кнопок
@dp.message(F.text.in_({
    "🛰 Космическая карта",
    "🌍 Экологические данные",
    "📰 Новости",
    "🗺️ Квест-трип по городу"
}))
async def handle_buttons(message: types.Message):
    await message.answer("TODO ⏳", reply_markup=main_menu_kb())


@dp.message(SurveyStates.QUESTION)
async def process_answer(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    async with await get_db() as conn:
        await conn.execute(
            "UPDATE users SET points = points + 1 WHERE id = $1",
            user_id
        )

    await message.answer("Спасибо за ответ! Ваш балл добавлен.", reply_markup=main_menu_kb())
    await state.clear()


class QuizStates(StatesGroup):
    CATEGORY_SELECTION = State()
    ANSWERING_QUESTION = State()


quiz_categories = {
    "satellites": {
        "title": "🛰 Спутники и миссии",
        "questions": [
            {
                "question": "Какая российская компания занимается разработкой малых спутниковых систем для мониторинга Земли?",
                "options": ["1️⃣ Роскосмос", "2️⃣ SR Space", "3️⃣ Сколково.", "4️⃣ Glavkosmos."],
                "correct": 1,
                "explanation": "✅ Правильный ответ: 2️⃣ SR Space \n SR Space разрабатывает спутниковые системы для экологического и климатического мониторинга."
            },
            {
                "question": "Какой космический телескоп, запущенный в 1990 году, стал символом глубоких космических наблюдений?",
                "options": ["1️⃣ Кеплер", "2️⃣ Хаббл", "3️⃣ Джеймс Уэбб.", "4️⃣ Чандра."],
                "correct": 1,
                "explanation": "✅ Правильный ответ: 2️⃣ Хаббл \n Хаббл до сих пор позволяет получать уникальные изображения Вселенной."
            },
            {
                "question": "Какая миссия доставила первых людей на Луну в 1969 году?",
                "options": ["1️⃣ Аполлон-11", "2️⃣ Аполлон-13", "3️⃣ Вояджер-1.", "4️⃣ Маринер-10."],
                "correct": 0,
                "explanation": "✅ Правильный ответ: 1️⃣ Аполлон-11 \n Аполлон-11 стал историческим прорывом в освоении луны и космоса."
            }
        ]
    },
    "ecology": {
        "title": "🌍 Земля и экология",
        "questions": [
            {
                "question": " Какой газ считается основным виновником парникового эффекта?",
                "options": ["1️⃣ Кислород", "2️⃣ Азот", "3️⃣ Углекислый газ.", "4️⃣ Водород."],
                "correct": 2,
                "explanation": "✅ Правильный ответ: 3️⃣ Углекислый газ \n Избыточное содержание CO₂ приводит к глобальному потеплению."
            },
            {
                "question": "Какую роль выполняют спутниковые системы, разработанные, например, SR Space, в экологическом мониторинге?",
                "options": ["1️⃣ Производят солнечную энергию", "2️⃣ Отслеживают изменения атмосферы и лесные пожары", "3️⃣ Моделируют землетрясения.", "4️⃣ Измеряют глубину океанов."],
                "correct": 1,
                "explanation": "✅ Правильный ответ: 2️⃣ Отслеживают изменения атмосферы и лесные пожары \n Такие спутники собирают данные о выбросах CO₂, температуре и активности очагов пожаров."
            },
            {
            "question": " Какую информацию предоставляют спутниковые данные для оценки состояния экосистем?",
                "options": ["1️⃣ Данные о температуре и влажности почвы", "2️⃣ Сведения о миграции животных", "3️⃣ Информацию о росте растительности и изменениях в лесном покрове.", "4️⃣ Измерение уровня ультрафиолетового излучения."],
                "correct": 2,
                "explanation": "✅Правильный ответ: 3️⃣ Информация о росте растительности и изменениях в лесном покрове \n Спутниковые данные, например, через анализ NDVI, позволяют отслеживать динамику вегетации."
            }
        ]
    },
     "rokets": {
        "title": "🚀 Ракеты и технологии",
        "questions": [
            {
                "question": " Как называется первая многоразовая ракета, разработанная компанией SpaceX?",
                "options": ["1️⃣ Falcon 1", "2️⃣ Falcon 9", "3️⃣ Falcon Heavy.", "4️⃣ Starship."],
                "correct": 1,
                "explanation": "✅ Правильный ответ: 2️⃣ Falcon 9 \n Многоразовость Falcon 9 позволила значительно снизить затраты на запуски."
            },
            {
                "question": "Как называется ракета-носитель, разрабатываемая компанией SR Space для вывода малых спутников на орбиту?",
                "options": ["1️⃣ США", "2️⃣ СССР", "3️⃣ Китай", "4️⃣ Великобритания"],
                "correct": 1,
                "explanation": "✅ Правильный ответ: 2️⃣ СССР \n СССР лидировал в ранних этапах ракетостроения."
            },
            {
            "question": " Какая страна первой разработала межконтинентальную баллистическую ракету?",
                "options": ["1️⃣ Данные о температуре и влажности почвы", "2️⃣ Сведения о миграции животных", "3️⃣ Информацию о росте растительности и изменениях в лесном покрове.", "4️⃣ Измерение уровня ультрафиолетового излучения."],
                "correct": 2,
                "explanation": "✅Правильный ответ: 3️⃣ Информация о росте растительности и изменениях в лесном покрове \n Спутниковые данные, например, через анализ NDVI, позволяют отслеживать динамику вегетации."
            }
        ]
    }
}


@dp.message(F.text == "🎓 Викторина о космосе")
async def start_quiz(message: types.Message, state: FSMContext):
    await state.update_data(
        used_categories=[],
        current_category=None,
        last_message_id=None
    )
    await show_category_selection(message, state)


async def show_category_selection(message: types.Message, state: FSMContext):
    data = await state.get_data()
    builder = InlineKeyboardBuilder()

    for category_id, category in quiz_categories.items():
        if category_id not in data.get('used_categories', []):
            encoded_id = urllib.parse.quote_plus(category_id)
            builder.button(
                text=category["title"],
                callback_data=f"cat_{encoded_id}"
            )

    builder.adjust(1)

    try:
        text = "🎯 Выберите категорию:" + ("\n\n✅ Пройденные категории отмечены" if data.get('used_categories') else "")

        if data.get('last_message_id'):
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=data['last_message_id'],
                text=text,
                reply_markup=builder.as_markup()
            )
        else:
            msg = await message.answer(text, reply_markup=builder.as_markup())
            await state.update_data(last_message_id=msg.message_id)

        await state.set_state(QuizStates.CATEGORY_SELECTION)

    except Exception as e:
        logger.error(f"Error showing categories: {str(e)}")
        await message.answer("⚠️ Ошибка при загрузке категорий")

@dp.callback_query(QuizStates.ANSWERING_QUESTION, F.data.startswith("ans_"))
async def handle_answer(callback: types.CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        category_id = data['current_category']
        question_index = data['current_question_index']

        category = quiz_categories[category_id]
        question = category["questions"][question_index]

        # Удаляем кнопки
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception as e:
            logger.error(f"Error removing buttons: {str(e)}")

        # Обработка ответа
        selected_answer = int(callback.data.split("_")[1])
        is_correct = selected_answer == question["correct"]

        # Обновляем баллы
        if is_correct:
            conn = await get_db()
            try:
                await conn.execute(
                    "UPDATE users SET points = points + 1 WHERE id = $1",
                    callback.from_user.id
                )
            finally:
                await conn.close()

        # Показываем результат
        explanation = (
            f"✅ Правильно! +1 балл 🎉\n{question['explanation']}"
            if is_correct else
            f"❌ Неверно! Правильный ответ: {question['options'][question['correct']]}\n{question['explanation']}"
        )
        await callback.message.answer(explanation)

        # Переход к следующему вопросу или завершение
        if is_correct:
            await state.update_data(current_question_index=question_index + 1)
            await ask_current_question(callback.message, state)
        else:
            await complete_category(callback.message, state)

        await callback.answer()

    except Exception as e:
        logger.error(f"Error handling answer: {str(e)}")
        await callback.answer("⚠️ Ошибка обработки ответа")


async def get_user_points(user_id: int) -> int:
    conn = await get_db()
    try:
        result = await conn.fetchval(
            "SELECT points FROM users WHERE id = $1",
            user_id
        )
        return result or 0
    finally:
        await conn.close()


async def complete_category(message: types.Message, state: FSMContext):
    data = await state.get_data()
    used = data.get('used_categories', [])
    category_id = data['current_category']

    if category_id not in used:
        used.append(category_id)
        await state.update_data(
            used_categories=used,
            current_category=None,
            current_question_index=0
        )

    await show_category_selection(message, state)


@dp.callback_query(QuizStates.CATEGORY_SELECTION, F.data.startswith("cat_"))
async def select_category(callback: types.CallbackQuery, state: FSMContext):
    try:
        # Декодируем category_id
        encoded_category = callback.data.split("_", 1)[1]
        category_id = urllib.parse.unquote_plus(encoded_category)

        logger.debug(f"Selected category ID: {category_id}")

        if category_id not in quiz_categories:
            logger.error(f"Category {category_id} not found in quiz_categories")
            await callback.answer("Категория не найдена!")
            return

        # Обновляем состояние
        await state.update_data(
            current_category=category_id,
            current_question_index=0,
            last_message_id=None
        )

        # Удаляем предыдущее сообщение
        try:
            await callback.message.delete()
        except Exception as e:
            logger.error(f"Error deleting message: {e}")

        # Запускаем первый вопрос
        await ask_current_question(callback.message, state)
        await callback.answer()

    except Exception as e:
        logger.error(f"Error in select_category: {str(e)}", exc_info=True)
        await callback.answer("⚠️ Ошибка при выборе категории")


async def ask_first_question(message: types.Message, state: FSMContext):
    data = await state.get_data()
    category = quiz_categories[data['current_category']]

    # Создаем клавиатуру для первого вопроса
    builder = InlineKeyboardBuilder()
    for i, option in enumerate(category["questions"][0]["options"]):
        builder.button(text=option, callback_data=f"ans_{i}")

    builder.adjust(1)

    msg = await message.answer(
        f"📚 {category['title']}\n\n"
        f"❓ {category['questions'][0]['question']}",
        reply_markup=builder.as_markup()
    )
    await state.update_data(
        question_index=0,
        last_message_id=msg.message_id
    )
    await state.set_state(QuizStates.ANSWERING_QUESTION)


async def ask_current_question(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        category_id = data['current_category']
        question_index = data['current_question_index']

        category = quiz_categories[category_id]
        questions = category["questions"]

        if question_index >= len(questions):
            await complete_category(message, state)
            return

        question = questions[question_index]

        # Создаем клавиатуру
        builder = InlineKeyboardBuilder()
        for i, option in enumerate(question["options"]):
            builder.button(text=option, callback_data=f"ans_{i}")
        builder.adjust(1)

        # Отправляем вопрос
        text = (
            f"📚 {category['title']}\n\n"
            f"❓ Вопрос {question_index + 1}/{len(questions)}:\n"
            f"{question['question']}"
        )

        msg = await message.answer(text, reply_markup=builder.as_markup())
        await state.update_data(last_message_id=msg.message_id)
        await state.set_state(QuizStates.ANSWERING_QUESTION)

    except Exception as e:
        logger.error(f"Error asking question: {str(e)}")
        await message.answer("⚠️ Ошибка при загрузке вопроса")


# Добавляем обработчик для выбора категорий
@dp.callback_query(F.data.startswith("cat_"))
async def handle_category_selection(callback: types.CallbackQuery, state: FSMContext):
    try:
        # Получаем и декодируем category_id
        encoded_category = callback.data.split("_", 1)[1]
        category_id = urllib.parse.unquote_plus(encoded_category)

        logger.info(f"Selected category: {category_id}")

        # Проверяем существование категории
        if category_id not in quiz_categories:
            logger.error(f"Category not found: {category_id}")
            await callback.answer("⚠️ Категория не найдена")
            return

        # Обновляем состояние
        await state.set_state(QuizStates.ANSWERING_QUESTION)
        await state.update_data(
            current_category=category_id,
            current_question_index=0,
            used_categories=[]
        )

        # Удаляем предыдущее сообщение
        try:
            await callback.message.delete()
        except Exception as e:
            logger.error(f"Error deleting message: {e}")

        # Запускаем первый вопрос
        await ask_current_question(callback.message, state)
        await callback.answer()

    except Exception as e:
        logger.error(f"Error in category selection: {str(e)}")
        await callback.answer("⚠️ Ошибка при выборе категории")


@dp.message()
async def unknown_message(message: types.Message):
    logger.warning(f"Unhandled message: {message.text}")
    await message.answer("Используйте кнопки меню для навигации")


async def main():
    conn = await get_db()
    try:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                points INTEGER DEFAULT 0
            )
        ''')
    finally:
        await conn.close()

    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())