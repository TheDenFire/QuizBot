import os
import logging
import traceback
import urllib
from datetime import datetime
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command, or_f, state
from aiogram.utils.chat_action import ChatActionSender
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiohttp import ClientError, TCPConnector

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
    async with ChatActionSender.typing(
            chat_id=message.chat.id,
            bot=message.bot
    ):
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
    "🌍 Экологические данные",
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


# Добавляем новые состояния
class MapStates(StatesGroup):
    MAIN_MENU = State()
    SATELLITE_LIST = State()
    SATELLITE_INFO = State()


# Список спутников

SATELLITES = {
    "voyager": {
        "name": "Voyager 1 (Вояджер-1)",
        "description": (
            "Voyager 1 (Вояджер-1) 🌌\n"
            "🌍 Орбита: Вышел за пределы Солнечной системы (24 млрд км от Земли)\n"
            "📊 Миссия: Исследование дальнего космоса и межзвездного пространства\n"
            "📷 Последние данные: https://voyager.jpl.nasa.gov/\n"
            "\n"
            "🔗 Подробнее:(https://voyager.jpl.nasa.gov/)\n\n"
        )
    },
    "hubble": {
        "name": "Hubble Space Telescope (Хаббл)",
        "description": (
            "🔭 Легендарный космический телескоп NASA\n\n"
            "• Запущен в 1990 году\n"
            "• Диаметр зеркала: 2.4 м\n"
            "• Орбита: 547 км\n"
            "• Сделал >1.5 млн наблюдений"
        )
    },
    "webb": {
        "name": "James Webb Space Telescope (Джеймс Уэбб)",
        "description": (
            "🌟 Новейший инфракрасный телескоп\n\n"
            "• Запущен в 2021 году\n"
            "• Диаметр зеркала: 6.5 м\n"
            "• Расположение: точка Лагранжа L2\n"
            "• Изучает раннюю Вселенную"
        )
    }
}

def get_satellite_names():
    return [sat["name"] for sat in SATELLITES.values()]

def find_satellite_by_name(name: str):
    return next((sat for sat in SATELLITES.values() if sat["name"] == name), None)

# Клавиатура главного меню карты
def map_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="Найти спутник"))
    builder.add(types.KeyboardButton(text="Показать карту всех спутников"))
    builder.add(types.KeyboardButton(text="Назад в главное меню"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


def satellites_list_kb():
    builder = ReplyKeyboardBuilder()
    # Извлекаем только названия спутников
    for sat in SATELLITES.values():
        builder.add(types.KeyboardButton(text=sat["name"]))  # Используем ключ "name"
    builder.add(types.KeyboardButton(text="Назад"))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


# Обработчик кнопки "Космическая карта"
@dp.message(F.text == "🛰 Космическая карта")
async def handle_space_map(message: types.Message, state: FSMContext):
    await state.set_state(MapStates.MAIN_MENU)
    await message.answer(
        "🌌 Добро пожаловать в раздел космической карты!\n"
        "Здесь вы можете отслеживать спутники SR Space и другие объекты.",
        reply_markup=map_menu_kb()
    )


# Обработчик кнопки "Найти спутник"
@dp.message(F.text == "Найти спутник")
async def search_satellite(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != MapStates.MAIN_MENU:
        await message.answer("Пожалуйста, вернитесь в главное меню карты")
        return

    await state.set_state(MapStates.SATELLITE_LIST)
    await message.answer(
        "🔍 Выберите спутник из списка:",
        reply_markup=satellites_list_kb()
    )


@dp.message(F.text.in_(get_satellite_names()), MapStates.SATELLITE_LIST)
async def show_satellite_info(message: types.Message, state: FSMContext):
    satellite = find_satellite_by_name(message.text)
    if not satellite:
        await message.answer("🚫 Спутник не найден")
        return

    await state.set_state(MapStates.SATELLITE_INFO)
    await state.update_data(current_satellite=satellite)

    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text="Назад к списку"))

    # Отправляем только текст
    await message.answer(
        f"🛰 {satellite['name']}\n\n{satellite['description']}",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )


# Обработчик кнопки "Назад"
@dp.message(F.text == "Назад к списку", MapStates.SATELLITE_INFO)
async def back_to_list(message: types.Message, state: FSMContext):
    await state.set_state(MapStates.SATELLITE_LIST)
    await message.answer(
        "🔍 Выберите спутник из списка:",
        reply_markup=satellites_list_kb()
    )


# Обработчик кнопки "Назад в главное меню"
@dp.message(F.text == "Назад", MapStates.SATELLITE_LIST)
async def back_to_map_menu(message: types.Message, state: FSMContext):
    await state.set_state(MapStates.MAIN_MENU)
    await message.answer(
        "Возвращаемся в меню карты:",
        reply_markup=map_menu_kb()
    )

@dp.message(F.text == "Показать карту всех спутников", MapStates.MAIN_MENU)
async def handle_back_to_main_menu(message: types.Message, state: FSMContext):
    await state.set_state(MapStates.MAIN_MENU)
    await message.answer(
        "🛰 Глобальная карта спутников\n"
        "\n"
        "🔍 Здесь можно увидеть все активные спутники в реальном времени!\n"
        "📡 Карта обновляется автоматически и показывает траектории движения.\n"
        "\n"
        "🔗https://spacegid.com/media/space_sattelite/",
        reply_markup=main_menu_kb()
    )

@dp.message(F.text == "Назад в главное меню")
async def handle_back_to_main_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Вы вернулись в главное меню:",
        reply_markup=main_menu_kb()
    )

# Обновляем старый обработчик для кнопки "Космическая карта"
@dp.message(F.text.in_({"🛰 Космическая карта"}))
async def handle_buttons(message: types.Message):
    await handle_space_map(message, message.bot, message.chat.id)


# ... предыдущий импорт ...
from aiogram.types import URLInputFile, InlineKeyboardButton


# Добавляем новые состояния
class NewsStates(StatesGroup):
    VIEWING_NEWS = State()


class AdminNewsStates(StatesGroup):
    ENTER_TEXT = State()
    ENTER_PHOTO = State()
    CONFIRMATION = State()


# ... остальной существующий код ...

# region News Section

async def get_news_list():
    conn = await get_db()
    try:
        return await conn.fetch("SELECT * FROM news ORDER BY created_at DESC")
    except Exception as e:
        logger.error(f"Ошибка получения новостей: {e}")
        return []
    finally:
        await conn.close()




@dp.message(F.text == "📰 Новости")
async def handle_news(message: types.Message, state: FSMContext):
    async with ChatActionSender.typing(
            chat_id=message.chat.id,
            bot=message.bot
    ):
        news_list = await get_news_list()
    if not news_list:
        await message.answer("📭 Пока нет новостей. Следите за обновлениями!")
        return

    await state.set_state(NewsStates.VIEWING_NEWS)
    await state.update_data(news_list=news_list, current_index=0)
    await show_news(message.from_user.id, state)


async def show_news(user_id: int, state: FSMContext):
    data = await state.get_data()
    news_list = data['news_list']
    current_index = data['current_index']

    try:
        news_item = news_list[current_index]
        text = f"📰 *{news_item['text']}\n\n*{news_item['created_at'].strftime('%d.%m.%Y')}"

        builder = InlineKeyboardBuilder()
        if current_index < len(news_list) - 1:
            builder.button(text="◀️ Предыдущая", callback_data="prev_news")
        builder.button(text="🏠 В меню", callback_data="news_back_to_menu")

        send_method = bot.send_photo if news_item['photo'] else bot.send_message
        content = {
            'chat_id': user_id,
            'caption' if news_item['photo'] else 'text': text,
            'parse_mode': "Markdown",
            'reply_markup': builder.as_markup()
        }

        if news_item['photo']:
            if news_item['photo'].startswith(('http', 'https')):
                content['photo'] = URLInputFile(news_item['photo'])
            else:
                content['photo'] = news_item['photo']

        message = await send_method(**content)
        await state.update_data(last_message_id=message.message_id)

    except Exception as e:
        logger.error(f"News display error: {str(e)}")
        await bot.send_message(
            chat_id=user_id,
            text="⚠️ Не удалось загрузить новость. Попробуйте позже."
        )


@dp.callback_query(NewsStates.VIEWING_NEWS, F.data == "prev_news")
async def prev_news(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_index = data['current_index']

    if current_index >= len(data['news_list']) - 1:
        await callback.answer("Это последняя новость")
        return

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass

    await state.update_data(current_index=current_index + 1)
    await show_news(callback.from_user.id, state)
    await callback.answer()


@dp.callback_query(NewsStates.VIEWING_NEWS, F.data == "news_back_to_menu")
async def news_back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb())
    await callback.answer()


# endregion

# region Admin News Management

async def is_admin(user_id: int):
    conn = await get_db()
    try:
        user = await conn.fetchrow("SELECT role FROM users WHERE id = $1", user_id)
        return user and user['role'] == 'admin'
    except Exception as e:
        logger.error(f"Ошибка проверки прав: {e}")
        return False
    finally:
        await conn.close()


@dp.message(Command("add_news"))
async def add_news_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав для выполнения этой команды")
        return

    await state.set_state(AdminNewsStates.ENTER_TEXT)
    await message.answer("📝 Введите текст новости:")


@dp.message(AdminNewsStates.ENTER_TEXT)
async def process_news_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.html_text)
    await state.set_state(AdminNewsStates.ENTER_PHOTO)
    await message.answer("📸 Пришлите фото для новости (или нажмите /skip чтобы пропустить)")


@dp.message(AdminNewsStates.ENTER_PHOTO, F.photo)
async def process_news_photo(message: types.Message, state: FSMContext):
    photo = message.photo[-1].file_id
    await state.update_data(photo=photo)
    await state.set_state(AdminNewsStates.CONFIRMATION)
    await request_confirmation(message, state)


@dp.message(AdminNewsStates.ENTER_PHOTO, Command("skip"))
async def skip_news_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo=None)
    await state.set_state(AdminNewsStates.CONFIRMATION)
    await request_confirmation(message, state)


async def request_confirmation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Опубликовать", callback_data="confirm_news")
    builder.button(text="❌ Отменить", callback_data="cancel_news")

    text = f"📝 *Текст новости:*\n{data['text']}\n\n"
    text += f"🖼 *Фото:* {'есть' if data.get('photo') else 'нет'}"

    if data.get('photo'):
        await message.answer_photo(
            photo=data['photo'],
            caption=text,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            text=text,
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )


# region Improved News Management

async def send_news_to_user(user_id: int, news_item: asyncpg.Record):
    max_retries = 5
    backoff_factor = 0.5

    for attempt in range(max_retries):
        try:
            text = f"📰 *{news_item['created_at'].strftime('%d.%m.%Y %H:%M')}*\n\n{news_item['text']}"

            if news_item['photo']:
                # Отправляем используя file_id напрямую
                await bot.send_photo(
                    chat_id=user_id,
                    photo=news_item['photo'],
                    caption=text,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode="Markdown"
                )
            return True

        except TelegramAPIError as e:
            wait_time = backoff_factor * (2 ** attempt)
            logger.warning(f"Retry {attempt + 1}/{max_retries} for user {user_id} in {wait_time:.1f}s")
            await asyncio.sleep(wait_time)

        except Exception as e:
            logger.error(f"Critical error for user {user_id}: {type(e).__name__} - {str(e)}")
            return False

    logger.error(f"Failed to send news to user {user_id} after {max_retries} attempts")
    return False


from aiogram.exceptions import TelegramBadRequest, TelegramAPIError


@dp.callback_query(AdminNewsStates.CONFIRMATION, F.data == "confirm_news")
async def confirm_news_publish(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    conn = await get_db()

    try:
        # Сохраняем новость с проверкой размера текста
        if len(data['text']) > 4000:
            raise ValueError("Text too long (max 4000 chars)")

        news = await conn.fetchrow(
            """INSERT INTO news (admin_id, text, photo)
            VALUES ($1, $2, $3)
            RETURNING *""",
            callback.from_user.id,
            data['text'][:4000],  # Обрезаем текст при необходимости
            data.get('photo')[:512] if data.get('photo') else None  # Ограничение длины URL
        )

        # Асинхронная рассылка с ограничением параллелизма
        users = await conn.fetch("SELECT id FROM users WHERE NOT is_banned")
        semaphore = asyncio.Semaphore(10)  # Максимум 10 одновременных отправок

        async def send_task(user):
            async with semaphore:
                return await send_news_to_user(user['id'], news)

        results = await asyncio.gather(*[send_task(user) for user in users])

        success_count = sum(results)
        failed_count = len(results) - success_count

        status_message = (
            f"📊 Статус рассылки:\n"
            f"• Успешно: {success_count}\n"
            f"• Не доставлено: {failed_count}\n"
            f"• Всего получателей: {len(users)}"
        )

        # Отправка отчета администратору
        report_text = status_message + f"\n\nТекст новости:\n{data['text'][:300]}..."

        try:
            if data.get('photo'):
                await callback.message.edit_caption(caption=report_text)
            else:
                await callback.message.edit_text(text=report_text)
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                raise

        # Логирование в отдельную таблицу
        await conn.execute(
            """INSERT INTO news_delivery_logs 
            (news_id, total_users, success_count) 
            VALUES ($1, $2, $3)""",
            news['id'], len(users), success_count
        )

    except ValueError as e:
        error_msg = f"❌ Ошибка: {str(e)}"
    except Exception as e:
        error_msg = "⚠️ Ошибка публикации! Проверьте данные и подключение"
        logger.error(f"Publish error: {traceback.format_exc()}")
    finally:
        await conn.close()
        await state.clear()


# endregion

@dp.callback_query(AdminNewsStates.CONFIRMATION, F.data == "cancel_news")
async def cancel_news_publish(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    if callback.message.photo:
        await callback.message.edit_caption("❌ Создание новости отменено")
    else:
        await callback.message.edit_text("❌ Создание новости отменено")
    await callback.answer()


class QuestStates(StatesGroup):
    CITY_INPUT = State()
    CONFIRMATION = State()
    QUEST_IN_PROGRESS = State()
    WAITING_PHOTO = State()


# Обработчик кнопки "Квест-трип по городу"
@dp.message(F.text == "🗺️ Квест-трип по городу")
async def start_quest(message: types.Message, state: FSMContext):
    await state.set_state(QuestStates.CITY_INPUT)
    await message.answer(
        "Приветствую тебя на пути изучения российской космонавтики! 🚀\n\n"
        "Тебя ждет путешествие по млечному пути космической истории внутри твоего города.\n\n"
        "Введи его название:"
    )


# Обработчик ввода города
@dp.message(QuestStates.CITY_INPUT)
async def process_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)

    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Запуск", callback_data="start_quest_confirmed")

    await message.answer(
        f"Прекрасно! Техника настроена, ракета готова к запуску!\n"
        f"Мы посетим 6 мест, решим 5 загадок и вместе погрузимся в космос твоего города. "
        f"А по окончанию путешествия тебя ждет подарок! Готов отправиться?",
        reply_markup=builder.as_markup()
    )
    await state.set_state(QuestStates.CONFIRMATION)


# Обработчик подтверждения начала квеста
@dp.callback_query(QuestStates.CONFIRMATION, F.data == "start_quest_confirmed")
async def start_quest_confirmed(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await send_quest_task(callback.message, state, task_number=1)
    await state.set_state(QuestStates.QUEST_IN_PROGRESS)


# Функция отправки задания
async def send_quest_task(message: types.Message, state: FSMContext, task_number: int):
    tasks = {
        1: {
            "text": "Он сказал: «Поехали»! – И вот первое задание квеста:\n\n"
                    "🗽 Задание 1: Космический Памятник\n\n"
                    "Найди в городе памятник или монумент, связанный с космонавтами или учеными.",
            "button": "Нашел ✅"
        }
    }

    task = tasks.get(task_number)
    if not task:
        return await finish_quest(message, state)

    builder = ReplyKeyboardBuilder()
    builder.button(text=task["button"])

    await message.answer(
        task["text"],
        reply_markup=builder.as_markup(resize_keyboard=True)
    )
    await state.update_data(current_task=task_number)


# Обработчик кнопки "Нашел ✅"
@dp.message(F.text == "Нашел ✅", QuestStates.QUEST_IN_PROGRESS)
async def found_monument(message: types.Message, state: FSMContext):
    await state.set_state(QuestStates.WAITING_PHOTO)
    await message.answer(
        "Теперь сделай фотографию у памятника, отправь ее мне с ответом на вопрос: "
        "«Кто изображен на памятнике и что он сделал для космонавтики?»",
        reply_markup=types.ReplyKeyboardRemove()
    )


# Обработчик фото и ответа
@dp.message(QuestStates.WAITING_PHOTO, F.photo)
async def process_quest_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()

    # Сохраняем в базу данных
    conn = await get_db()
    try:
        await conn.execute(
            "INSERT INTO quest_submissions "
            "(user_id, city, task_number, photo_id, answer, submission_time) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            message.from_user.id,
            data['city'],
            data['current_task'],
            message.photo[-1].file_id,
            message.caption or "",
            datetime.now()
        )

        # Начисляем баллы
        await conn.execute(
            "UPDATE users SET points = points + 10 WHERE id = $1",
            message.from_user.id
        )
    finally:
        await conn.close()

    # Уведомляем админов
    await notify_admins(message, state)

    await message.answer(
        "✅ Отлично! Ты прошел первый этап квеста!\n"
        "Следующее задание появится совсем скоро...",
        reply_markup=main_menu_kb()
    )
    await state.clear()


# Функция уведомления админов
async def notify_admins(message: types.Message, state: FSMContext):
    data = await state.get_data()  # Теперь state передается как аргумент

    conn = await get_db()
    try:
        admins = await conn.fetch(
            "SELECT id FROM users WHERE role = 'admin'"
        )

        report_text = (
            "🚨 Новое выполнение квеста!\n"
            f"👤 Пользователь: @{message.from_user.username}\n"
            f"🏙 Город: {data['city']}\n"  # Берем city из данных состояния
            f"📷 Фото: {message.photo[-1].file_id}"
        )

        for admin in admins:
            try:
                await bot.send_photo(
                    chat_id=admin['id'],
                    photo=message.photo[-1].file_id,
                    caption=report_text
                )
            except Exception as e:
                logger.error(f"Error sending to admin {admin['id']}: {e}")

    finally:
        await conn.close()


# Функция завершения квеста
async def finish_quest(message: types.Message, state: FSMContext):
    await message.answer(
        "🎉 Поздравляем! Ты успешно завершил квест-трип!\n"
        "Твой подарок: +50 баллов в профиль!\n"
        "Следующий квест появится совсем скоро...",
        reply_markup=main_menu_kb()
    )
    await state.clear()








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
    data = await state.get_data()

    # Проверяем активна ли категория
    if data.get('used_categories'):
        await message.answer("🚫 Завершите текущую категорию сначала!")
        return

    await state.update_data(
        used_categories=[],
        current_category=None,
        last_message_id=None
    )
    await show_category_selection(message, state)


async def show_category_selection(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.chat.id
    completed = await QuizManager.get_completed_categories(user_id)
    used_categories = data.get('used_categories', [])  # Добавляем получение used_categories
    print(f"show_category_selection: User ID from message: {user_id}")
    print(f"[DEBUG] Completed categories: {completed}")

    builder = InlineKeyboardBuilder()

    for category_id, category in quiz_categories.items():
        is_used = category_id in used_categories
        is_completed = category_id in completed
        print(f"[DEBUG] Category {category_id} completed: {is_completed}")

        safe_category_id = category_id.replace(" ", "_").lower()

        button_text = f"{'✅ ' if is_completed else ''}{category['title']}"

        # Если категория уже используется, делаем кнопку неактивной
        builder.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"cat_{safe_category_id}" if not is_used else "ignore", # Используем нормализованный ID
            )
        )

    # builder.row(types.InlineKeyboardButton(
    #     text="⬅️ Назад",
    #     callback_data="back_to_main"
    # ))


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

        if not builder.buttons:
            text = "🎉 Вы прошли все категории!"

        await state.set_state(QuizStates.CATEGORY_SELECTION)

    except Exception as e:
        logger.error(f"Error showing categories: {str(e)}")
        await message.answer("⚠️ Ошибка при загрузке категорий")

@dp.callback_query(F.data == "ignore")
async def handle_ignore(callback: types.CallbackQuery):
    await callback.answer("🚫 Эта категория уже начата!", show_alert=True)

@dp.callback_query(QuizStates.ANSWERING_QUESTION, F.data.startswith("ans_"))
async def handle_answer(callback: types.CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        category_id = data['current_category']
        question_index = data['current_question_index']

        category = quiz_categories[category_id]
        questions = category["questions"]
        question = questions[question_index]

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

        new_question_index = question_index + 1
        await state.update_data(current_question_index=new_question_index)

        # Переход к следующему вопросу или завершение
        if new_question_index < len(questions):
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
    category_id = data.get('current_category')

    await state.update_data(
        used_categories=[],
        current_category=None  # Важно сбросить текущую категорию
    )

    if category_id:
        await QuizManager.complete_category(message.chat.id, category_id)

    await show_category_selection(message, state)


@dp.message(Command("resetquiz"))
async def resetquiz_command(message: types.Message):
    # Получаем информацию о пользователе из БД
    conn = await get_db()
    user = await conn.fetchrow(
        "SELECT role FROM users WHERE id = $1",
        message.from_user.id
    )

    if not user or user['role'] != 'admin':
        return await message.answer("⛔ Недостаточно прав!")

    await QuizManager.reset_all_progress()
    await message.answer("♻ Прогресс всех пользователей сброшен!")


# @dp.callback_query(QuizStates.CATEGORY_SELECTION, F.data.startswith("cat_"))
# async def select_category(callback: types.CallbackQuery, state: FSMContext):
#     try:
#         # Декодируем category_id
#         encoded_category = callback.data.split("_", 1)[1]
#         category_id = urllib.parse.unquote_plus(encoded_category)
#
#         logger.debug(f"Selected category ID: {category_id}")
#
#         if category_id not in quiz_categories:
#             logger.error(f"Category {category_id} not found in quiz_categories")
#             await callback.answer("Категория не найдена!")
#             return
#
#         # Обновляем состояние
#         await state.update_data(
#             current_category=category_id,
#             current_question_index=0,
#             last_message_id=None
#         )
#
#         # Удаляем предыдущее сообщение
#         try:
#             await callback.message.delete()
#         except Exception as e:
#             logger.error(f"Error deleting message: {e}")
#
#         # Запускаем первый вопрос
#         await ask_current_question(callback.message, state)
#         await callback.answer()
#
#     except Exception as e:
#         logger.error(f"Error in select_category: {str(e)}", exc_info=True)
#         await callback.answer("⚠️ Ошибка при выборе категории")


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
        completed = await QuizManager.get_completed_categories(callback.from_user.id)

        data = await state.get_data()
        used_categories = data.get('used_categories', [])
        print(f"User ID from message: {callback.from_user.id}")

        logger.info(f"Selected category: {category_id}")

        # Проверяем существование категории
        if category_id in completed:
            await callback.answer("❌ Категория уже пройдена!")
            return

        if category_id not in quiz_categories:
            await callback.answer("⚠️ Категория не найдена")
            return

        if used_categories:
            await callback.answer("🚫 Завершите текущую категорию сначала!", show_alert=True)
            return
        # Обновляем состояние
        await state.set_state(QuizStates.ANSWERING_QUESTION)
        await state.update_data(
            current_category=category_id,
            current_question_index=0,
            used_categories=[category_id]
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


class QuizManager:
    @staticmethod
    async def get_completed_categories(user_id: int) -> set:
        conn = await get_db()
        result = await conn.fetch(
            "SELECT category_id FROM completed_categories WHERE user_id = $1",
            user_id
        )
        return {row['category_id'] for row in result}

    @staticmethod
    async def complete_category(user_id: int, category_id: str):
        conn = await get_db()
        await conn.execute(
            """INSERT INTO completed_categories (user_id, category_id)
               VALUES ($1::BIGINT, $2::VARCHAR)
               ON CONFLICT DO NOTHING""",
            user_id, category_id
        )

    @staticmethod
    async def reset_all_progress():
        conn = await get_db()
        await conn.execute("TRUNCATE TABLE completed_categories")

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
        # Создаем таблицу quest_submissions
        await conn.execute('''
                    CREATE TABLE IF NOT EXISTS quest_submissions (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(id),
                        city TEXT,
                        task_number INTEGER,
                        photo_id TEXT,
                        answer TEXT,
                        submission_time TIMESTAMP
                    )
                ''')
        # для учета пройденных категорий
        await conn.execute('''CREATE TABLE IF NOT EXISTS completed_categories
             (user_id INTEGER, 
              category_id TEXT,
              PRIMARY KEY (user_id, category_id))''')
    finally:
        await conn.close()

    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())