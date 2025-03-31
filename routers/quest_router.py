from aiogram import F, Router, types, Bot
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from datetime import datetime
from aiogram.fsm.state import StatesGroup, State
from states import QuestStates
from database import get_db

import logging

quest_router = Router()
logger = logging.getLogger(__name__)

QUEST_COMPLIMENTS = {
    1: "Вот это кадр! Такой ракурс смогли бы подобрать разве что только спутники SR space!",
    2: "Материалы получены! Эту фотографию можно даже на карту GPS ставить!",
    3: "Экспонат как на подбор! Музей гордится твоим выбором!",
    4: "Ракета удалась! Прямо как настоящий инженерный проект!",
    5: "Вот это точность! Ты точно человек?",
    6: "Загадка разгадана! Ты настоящий космический детектив!",
    7: "Получено! В тебе зарождается профессиональный писатель!",
    8: "Правильно! SR Space гордится тобой!",
    9: "Идеальное расположение для космической литературы!",
    10: "Отчет принят! Твои данные отправлены в ЦУП!",
    11: "Фото принято! Ты завершил космическую одиссею!"
}


async def ask_continue_or_restart(message: types.Message, progress: dict):
    """Спрашивает продолжить или начать заново"""
    builder = InlineKeyboardBuilder()
    builder.button(text="▶️ Продолжить", callback_data=f"continue_{progress['current_task']}")
    builder.button(text="🔄 Начать заново", callback_data="restart_confirm")
    builder.adjust(1)

    await message.answer(
        f"Найден сохранённый прогресс: задание {progress['current_task']} в городе {progress['city']}.\n"
        "Выберите действие:",
        reply_markup=builder.as_markup()

    )

                     # Старт квеста и выбор города
@quest_router.message(F.text == "🗺️ Квест-трип по городу")
async def start_quest(message: types.Message, state: FSMContext):
    conn = await get_db()
    try:
        # Проверяем существующий прогресс
        progress = await conn.fetchrow(
            "SELECT current_task, city FROM user_progress WHERE user_id = $1",
            message.from_user.id
        )

        if progress:
            await state.update_data(
                current_task=progress['current_task'],
                city=progress['city']
            )
            await ask_continue_or_restart(message, progress)  # Запрашиваем выбор
            await state.set_state(QuestStates.CONFIRM_RESET)
        else:
            await state.update_data(current_task=1)
            await message.answer("Приветствую тебя на пути изучения российской космонавтики! 🚀\n"
                            "\n"
                                "Тебя ждет путешествие по млечному пути космической истории внутри твоего города.\n" 
                                        "\n"
                            "Введи его название:")
            await state.set_state(QuestStates.CITY_INPUT)

    except Exception as e:
        logger.error(f"Ошибка старта квеста: {e}")
    finally:
        await conn.close()

# Обработчики кнопок
@quest_router.callback_query(F.data.startswith("continue_"))
async def handle_continue(callback: types.CallbackQuery, state: FSMContext):
    task_number = int(callback.data.split("_")[1])
    await callback.message.delete()
    await TASK_HANDLERS[task_number](callback.message, state)
    await callback.answer()


@quest_router.callback_query(F.data == "restart_confirm")
async def handle_restart_confirm(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="restart_final")
    builder.button(text="❌ Отмена", callback_data="cancel_restart")

    await callback.message.edit_text(
        "Вы уверены, что хотите начать заново? Весь прогресс будет удалён!",
        reply_markup=builder.as_markup()
    )
    await callback.answer()


@quest_router.callback_query(F.data == "restart_final")
async def handle_restart_final(callback: types.CallbackQuery, state: FSMContext):
    # Сбрасываем прогресс в БД
    conn = await get_db()
    try:
        await conn.execute(
            "DELETE FROM user_progress WHERE user_id = $1",
            callback.from_user.id
        )
    finally:
        await conn.close()

    await state.clear()
    await callback.message.edit_text("Прогресс сброшен! Начинаем сначала.")
    # Запускаем начальное состояние
    await callback.message.answer(
        "Приветствую тебя на пути изучения российской космонавтики! 🚀\n"
        "Введи название своего города:"
    )
    await state.set_state(QuestStates.CITY_INPUT)
    await callback.answer()

@quest_router.callback_query(F.data == "cancel_restart")
async def handle_cancel_restart(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.answer("Отмена сброса прогресса")

# Базовые функции
async def save_submission(user_id: int, task: int, data: dict, city: str, message: types.Message = None):
    conn = await get_db()
    try:
        await conn.execute(
            """INSERT INTO quest_submissions 
            (user_id, city, task_number, photo_id, answer, submission_time)
            VALUES ($1, $2, $3, $4, $5, $6)""",
            user_id,
            city,
            task,
            data.get('photo'),
            data.get('answer'),
            datetime.now()
        )

        # Отправляем отчет после сохранения
        if message:
            await send_admin_report(
                bot=message.bot,
                user_id=user_id,
                task_number=task,
                answer=data.get('answer'),
                photo_id=data.get('photo'),
                city=city
            )
    finally:
        await conn.close()


async def handle_generic_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    current_task = data['current_task']
    city = data['city']  # Получаем город из состояния

    await save_submission(
        user_id=message.from_user.id,
        task=current_task,
        data={'photo': message.photo[-1].file_id, 'answer': message.caption},
        city=city  # Передаем в функцию
    )


async def show_next_button(message: types.Message, current_task: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="Далее ➡️", callback_data=f"next_{current_task}")

    await message.answer(
        "Готовы к следующему заданию?",
        reply_markup=builder.as_markup()
    )


import logging
logger = logging.getLogger(__name__)


@quest_router.message(QuestStates.CITY_INPUT)
async def handle_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)
    await message.answer("Прекрасно! Техника настроена, ракета готова к запуску!\n"
                        "Мы посетим 6 мест, решим 5 загадок и вместе погрузимся в космос твоего города. А по окончанию путешествия тебя ждет подарок! Готов отправиться?")
    builder = ReplyKeyboardBuilder()
    await start_task_1(message, state)


# Задание 1 - Памятник
async def start_task_1(message: types.Message, state: FSMContext):
    await state.update_data(current_task=1)
    builder = ReplyKeyboardBuilder()
    builder.button(text="Нашел памятник ✅")

    await message.answer(
        "Он сказал: «Поехали»! – И вот первое задание квеста:\n"
        "🗽 Задание 1: Космический Памятник\n"
        "Найди в городе памятник или монумент, связанный с космонавтами или учеными.",
        reply_markup=builder.as_markup(resize_keyboard=True, one_time_keyboard=True)  # Автоскрытие
    )
    await state.set_state(QuestStates.TASK1_PHOTO)
# Задание 1 - Обработка кнопки и фото
@quest_router.message(QuestStates.TASK1_PHOTO, F.text == "Нашел памятник ✅")
async def handle_task1_button_press(message: types.Message):
    """Обрабатываем повторное нажатие кнопки"""
    await message.answer("Теперь сделай фотографию у памятника, отправь ее мне с ответом на вопрос: «Кто изображен на памятнике и что он сделал для космонавтики?»")

@quest_router.message(QuestStates.TASK1_PHOTO, F.photo)
async def handle_task1_photo(message: types.Message, state: FSMContext):
    try:
        await handle_generic_photo(message, state)
        await message.answer("Вот это кадр! Такой ракурс смогли бы подобрать разве что только спутники SR space!")
        data = await state.get_data()
        await save_submission(
            user_id=message.from_user.id,
            task=1,
            data={
                'photo': message.photo[-1].file_id,
                'answer': message.caption
            },
            city=data['city'],
            message=message  # Передаем сообщение для доступа к bot
        )
        await start_task_2(message, state)  # <-- Добавьте эту строку
    except Exception as e:
        logger.error(f"Ошибка: {e}")

@quest_router.message(QuestStates.TASK1_PHOTO)
async def handle_invalid_content(message: types.Message):
    """Ловим все неподходящие сообщения"""
    await message.answer("❌ Пожалуйста, отправь фотографию памятника!")
# Задание 2 - Улица
# Задание 2 - Улица (обновлено)
async def start_task_2(message: types.Message, state: FSMContext):
    await state.update_data(current_task=2)

    builder = ReplyKeyboardBuilder()
    builder.button(text="Нашел улицу ✅")
    builder.button(text="🚪 Выйти в меню")

    await message.answer(
        "🌃 Задание 2: Космические Улицы\n"
        "Найди на карте своего города улицы или переулки, названные в честь космонавтов или ученых.",
        reply_markup=builder.as_markup(
            resize_keyboard=True,
            one_time_keyboard=True  # Клавиатура скроется после использования
        )
    )
    await state.set_state(QuestStates.TASK2_PHOTO)
    logger.debug("Задание 2: состояние TASK2_PHOTO установлено")  # Логирование

# 2. Модифицируйте обработчик фото для задания 2
@quest_router.message(QuestStates.TASK2_PHOTO, F.photo)
async def handle_task2_photo(message: types.Message, state: FSMContext):
    try:
        # Сохраняем фото
        # await handle_generic_photo(message, state)

        await save_submission(
            user_id=message.from_user.id,
            task=2,
            data={'photo': message.photo[-1].file_id},
            city=(await state.get_data())['city'],
            message=message
        )
        # Запрашиваем текстовый ответ
        await message.answer(
            "📝 Теперь ответь: «Кто дал имя этой улице и что он сделал для космонавтики?»",
            reply_markup=types.ReplyKeyboardRemove()  # Убираем кнопки
        )
        await state.set_state(QuestStates.TASK2_TEXT)

    except Exception as e:
        logger.error(f"Ошибка обработки задания 2: {e}")
        await message.answer("⚠️ Что-то пошло не так. Попробуй еще раз.")
@quest_router.message(QuestStates.TASK2_PHOTO, F.text == "Нашел улицу ✅")
async def handle_task2_button(message: types.Message):
    """Обрабатываем нажатие кнопки и напоминаем отправить фото"""
    await message.answer("📸 Отлично! Теперь отправь фотографию улицы с названием.")


@quest_router.message(QuestStates.TASK2_TEXT)
async def handle_task2_text(message: types.Message, state: FSMContext):
    logger.debug(f"Получен ответ на задание 2: {message.text}")

    try:
        # Сохраняем ответ
        data = await state.get_data()
        await save_submission(
            user_id=message.from_user.id,
            task=2,
            data={'answer': message.text},  # Убрано поле photo
            city=data['city'],
            message=message
        )

        # Отправляем кнопку "Далее"
        await show_next_button(message, 2)
        logger.debug("Ответ сохранен, кнопка 'Далее' отправлена")

    except Exception as e:
        logger.error(f"Ошибка сохранения: {str(e)}")
        await message.answer("⚠️ Не удалось сохранить ответ. Попробуйте еще раз.")
# Задание 3 - Музей
async def start_task_3(message: types.Message, state: FSMContext):
    await state.update_data(current_task=3)

    builder = ReplyKeyboardBuilder()
    builder.button(text="Нашел экспонат ✅")
    builder.button(text="🚪 Выйти в меню")

    await message.answer(
        "🏛️ Задание 3: Космическая Выставка\n"
        "Найди ключевой экспонат и пришли его фото с описанием",
        reply_markup=builder.as_markup(
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    await state.set_state(QuestStates.TASK3_PHOTO)
    logger.debug("Состояние TASK3_PHOTO установлено")  # Логирование

@quest_router.message(QuestStates.TASK3_PHOTO, F.text == "Нашел экспонат ✅")
async def handle_task3_button(message: types.Message):
    """Обработка нажатия кнопки и напоминание отправить фото"""
    await message.answer("📸 Отлично! Теперь отправь фотографию экспоната.")


@quest_router.message(QuestStates.TASK3_PHOTO, F.photo)
async def handle_task3_photo(message: types.Message, state: FSMContext):
    try:
        # Сохраняем фото
        await handle_generic_photo(message, state)

        data = await state.get_data()
        await save_submission(
            user_id=message.from_user.id,
            task=3,
            data={
                'photo': message.photo[-1].file_id,
                'answer': message.caption
            },
            city=data['city'],
            message=message
        )

        await show_next_button(message, 3)

    except Exception as e:
        logger.error(f"Ошибка задания 3: {str(e)}")
        await message.answer("⚠️ Не удалось обработать фото. Попробуйте снова.")


# Задание 4 - Ракеты
async def start_task_4(message: types.Message, state: FSMContext):
    builder = ReplyKeyboardBuilder()
    builder.button(text="Нашел ракеты ✅")
    # Добавляем кнопку выхода через adjust (рядом с другими кнопками)
    builder.button(text="🚪 Выйти в меню")
    builder.adjust(1, 1)  # Первая кнопка в первом ряду, выход во втором

    await message.answer(
        "⚙️ Задание 4: Технологический прогресс\n"
        "Отыщи в музее фотографию или макет самой первой и самой современной ракеты.",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )
    await state.set_state(QuestStates.TASK4_PHOTO)

@quest_router.message(QuestStates.TASK4_PHOTO, F.text == "Нашел ракеты ✅")
async def handle_task4_button(message: types.Message):
    await message.answer("📸 Отправь фотографию ракет с подписью «Старая vs Новая»")


@quest_router.message(QuestStates.TASK4_PHOTO, F.photo)
async def handle_task4_photo(message: types.Message, state: FSMContext):
    # Запрашиваем текстовый ответ
    await state.update_data(task4_photo=message.photo[-1].file_id)

    await message.answer(
        "📝 Теперь напиши, в чем современная ракета лучше старой?",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(QuestStates.TASK4_TEXT)


@quest_router.message(QuestStates.TASK4_TEXT)
async def handle_task4_text(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()

        # Получаем file_id из предыдущего шага (фото сохраняется в состоянии)
        state_data = await state.get_data()
        photo_file_id = state_data.get('task4_photo')

        # Сохраняем ответ
        await save_submission(
            user_id=message.from_user.id,
            task=4,
            data={
                'photo': photo_file_id,  # Берем из состояния
                'answer': message.text  # Исправлено: message.text вместо caption
            },
            city=data['city'],
            message=message
        )

        # Кнопка продолжения
        builder = InlineKeyboardBuilder()
        builder.button(text="Следующее задание ➡️", callback_data="next_4")

        await message.answer(
            "🚀 Отличное сравнение! Ты настоящий космический инженер!",
            reply_markup=builder.as_markup()
        )

    except Exception as e:
        logging.error(f"Ошибка в задании 4: {e}")
        await message.answer("❌ Произошла ошибка. Попробуй еще раз.")

# Задание 5 - Спутник
async def start_task_5(message: types.Message, state: FSMContext):
    builder = ReplyKeyboardBuilder()
    builder.button(text="Нашел ✅")
    builder.button(text="🚪 Выйти в меню")

    await message.answer(
        "🌌 Задание 5: Поиск среди звезд\n"
        "Используя карту /map, найди местоположение спутника и сфотографируй экран",
        reply_markup=builder.as_markup()
    )
    await state.set_state(QuestStates.TASK5_PHOTO)

@quest_router.message(QuestStates.TASK5_PHOTO, F.text == "Нашел ✅")
async def handle_task5_button(message: types.Message):
    await message.answer("📸 Отправь фотографию")

@quest_router.message(QuestStates.TASK5_PHOTO, F.photo)
async def handle_task5_photo(message: types.Message, state: FSMContext):
    # Сохраняем фото
    await save_submission(
        user_id=message.from_user.id,
        task=5,
        data={'photo': message.photo[-1].file_id},
        city=(await state.get_data())['city']
    )

    # Запрашиваем текстовый ответ
    await message.answer(
        "Отличная фотография !",
        reply_markup=types.ReplyKeyboardRemove()
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="Следующее задание ➡️", callback_data="next_6")
    await show_next_button(message, 5)
    await state.set_state(QuestStates.TASK4_TEXT)


# Задание 6 - Загадка
async def start_task_6(message: types.Message, state: FSMContext):
    await message.answer(
        "❓Задание 6: Космическая Загадка\n\n"
        "Реши загадку о следующем месте, а затем отправься туда:\n"
        "\n"
        "В храме мудрости, где знания спят,\n"
        "Сокровищница мысли, где секреты хранят.\n"
        "Не в лаборатории, не в зале славы,\n"
        "А в месте, где прошлое и настоящее встречаются.\n\n"
        "Его стены — это ворота в прошлое,\n"
        "А полки — это мосты в будущее.\n"
        "Здесь хранятся истории о звездах и земле,\n"
        "И о том, как люди достигли космических высот"
    )
    await state.set_state(QuestStates.TASK6_ANSWER)


@quest_router.message(QuestStates.TASK6_ANSWER)
async def handle_task6_answer(message: types.Message, state: FSMContext):
    if message.text.lower() == "библиотека" or "Библиотека":
        data = await state.get_data()

        # Получаем file_id из предыдущего шага (фото сохраняется в состоянии)
        state_data = await state.get_data()
        photo_file_id = state_data.get('task4_photo')

        # Сохраняем ответ
        await save_submission(
            user_id=message.from_user.id,
            task=4,
            data={
                'photo': photo_file_id,  # Берем из состояния
                'answer': message.text  # Исправлено: message.text вместо caption
            },
            city=data['city'],
            message=message
        )
        await show_next_button(message, 6)
    else:
        await message.answer("Неверно, попробуй еще раз!")


# Задание 7 - Загадка (обновлено)
async def start_task_7(message: types.Message, state: FSMContext):
    await message.answer(
        "📚 Задание 7: Сотворение космоса и истины о нем\n\n"
        "Тебя уже ждут в библиотеке!\n"
        "Найди раздел о космонавтике. Выберите одну книгу о космосе и расскажи мне, о чем она. Лучшие описания книг я передаю для публикации в нашем официальном канале, а авторы получают дополнительной подарок, поэтому постарайся!"
    )
    await state.set_state(QuestStates.TASK7_ANSWER)

@quest_router.message(QuestStates.TASK7_ANSWER)
async def handle_task7_answer(message: types.Message, state: FSMContext):
    await message.answer("Получено! Как здорово вышло! Похоже, в тебе зарождается профессиональный искусственный интеллект по написанию текстов!")
    data = await state.get_data()

    # Получаем file_id из предыдущего шага (фото сохраняется в состоянии)
    state_data = await state.get_data()
    photo_file_id = state_data.get('task4_photo')

    # Сохраняем ответ
    await save_submission(
        user_id=message.from_user.id,
        task=4,
        data={
            'photo': photo_file_id,  # Берем из состояния
            'answer': message.text  # Исправлено: message.text вместо caption
        },
        city=data['city'],
        message=message
    )
    await show_next_button(message, 7)
    await state.set_state(QuestStates.TASK8_ANSWER)


# Задание 8 - Компания
# Задание 8 - Название компании и фото (обновлено)
async def start_task_8(message: types.Message, state: FSMContext):
    builder = ReplyKeyboardBuilder()
    builder.button(text="🚪 Выйти в меню")
    await message.answer(
        "Задание 8: Достижения на полке\n\n"
        "В настоящее время преемником советского союза в области космических достижений является компания, ставящая своей миссией — сделать космос доступным для решения глобальных проблем человечества. Попробуешь угадать её название?\n",
        reply_markup=builder.as_markup(resize_keyboard=True, one_time_keyboard=True))
    await state.set_state(QuestStates.TASK8_ANSWER)

@quest_router.message(QuestStates.TASK8_ANSWER)
async def handle_task8_answer(message: types.Message, state: FSMContext):
    user_answer = message.text.strip().lower()

    if user_answer in {"sr space", "srspace", "ср спейс"}:
        await message.answer(
            "Верно !\n\n📸 Не покидая библиотеки, найди место, где могла бы оказаться книга о новых достижениях в области российской космонавтики нашего столетия, совершенных данной компанией, и пришли мне фото.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(QuestStates.TASK8_PHOTO)
    else:
        await message.answer("Неверно, попробуй еще! 🔍")

@quest_router.message(QuestStates.TASK8_PHOTO, F.photo)
async def handle_task8_photo(message: types.Message, state: FSMContext):
    # Сохраняем фото
    data = await state.get_data()

    # Получаем file_id из предыдущего шага (фото сохраняется в состоянии)
    state_data = await state.get_data()
    photo_file_id = state_data.get('task4_photo')

    # Сохраняем ответ
    await save_submission(
        user_id=message.from_user.id,
        task=4,
        data={
            'photo': photo_file_id,  # Берем из состояния
            'answer': message.text  # Исправлено: message.text вместо caption
        },
        city=data['city'],
        message=message
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Следующее задание ➡️", callback_data="next_8")

    await message.answer(
        "📸 Отличный выбор! Именно здесь мы разместим книгу о наших достижениях!",
        reply_markup=builder.as_markup()
    )


# Задание 9 - Фото книги
async def start_task_9(message: types.Message, state: FSMContext):
    builder = ReplyKeyboardBuilder()
    builder.button(text="Назад в меню")

    await message.answer(
        "🛰️ Задание 10: Будущее российской космонавтики\n"
        "Описание: SR Space – частная российская космическая компания, активно развивает российскую частную космонавтику и внедряет инновационные технологии в сферу космоса для улучшения качества жизни на Земле.\n\n"
        "Напишите краткий отчет (3-5 предложений) о самых весомых проектах компании на твой взгляд и их значении для российской космонавтики. Ты можешь воспользоваться сайтом компании и ее социальными сетями: \n\n"
        "https://srspace.ru/en\n\n"
        "https://t.me/srspaceru\n\n"
        "https://vk.com/srspaceru\n",
        reply_markup=builder.as_markup()
    )
    await state.set_state(QuestStates.TASK9_TEXT)


@quest_router.message(QuestStates.TASK9_TEXT)
async def handle_task9_text(message: types.Message, state: FSMContext):
    # Сохраняем ответ пользователя
    data = await state.get_data()

    # Получаем file_id из предыдущего шага (фото сохраняется в состоянии)
    state_data = await state.get_data()
    photo_file_id = state_data.get('task4_photo')

    # Сохраняем ответ
    await save_submission(
        user_id=message.from_user.id,
        task=4,
        data={
            'photo': photo_file_id,  # Берем из состояния
            'answer': message.text  # Исправлено: message.text вместо caption
        },
        city=data['city'],
        message=message
    )

    # Отправляем подготовленные сообщения
    responses = [
        "SR Space активно участвует в организации и проведении космических миссий, включая запуск спутников и исследовательских аппаратов. Компания уже успешно осуществила несколько запусков, которые способствовали развитию научных исследований и технологий научно-исследовательских центров мира.\n\n"
        "Разработанное компанией программное обеспечение для моделирования климатических изменений и оценки воздействия различных факторов на климат помогает в планировании мер по смягчению последствий человеческого влияния на окружающую среду.\n\n"
        "Еще больше интересных фактов ты узнаешь в социальных сетях компании или можешь попросить меня рассказать больше",
        "Спутниковые технологии компании используются для мониторинга загрязнения воздуха в реальном времени, что позволяет принимать оперативные меры для улучшения экологической ситуации.\n\n"
        "При помощи изображений, полученных со спутников компании, происходит отслеживание изменения в экосистемах и биоразнообразии, что важно для сохранения природных ресурсов.\n\n"
        "А проведенная ими интеграция IoT-устройств со спутниковыми системами для сбора и передачи данных в реальном времени с пользой применяется в различных отраслях, включая сельское хозяйство и охрану окружающей среды.\n\n"
        "Таким образом, разработки компании «SR Space» играют ключевую роль в решении глобальных проблем, обеспечивая инновационные подходы и технологии для мониторинга, анализа и связи.",
    ]

    for text in responses:
        await message.answer(text) # Пауза между сообщениями

    # Кнопка продолжения
    builder = InlineKeyboardBuilder()
    builder.button(text="Перейти к финалу ➡️", callback_data="next_9")

    await message.answer(
        "Теперь ты настоящий эксперт в космических технологиях!",
        reply_markup=builder.as_markup()
    )


# Задание 10 - Отчет
async def start_task_10(message: types.Message, state: FSMContext):
    builder = ReplyKeyboardBuilder()

    await message.answer(
        "Задание 10: Созерцание\n"
        "Сделай фотографию с ним (на фото должно быть не меньше двух людей)",
        reply_markup=builder.as_markup()
    )
    await state.set_state(QuestStates.TASK10_REPORT)


@quest_router.message(QuestStates.TASK10_REPORT, F.photo)
async def handle_task10_photo(message: types.Message, state: FSMContext):
    # Сохраняем фото
    await save_submission(
        user_id=message.from_user.id,
        task=10,
        data={'photo': message.photo[-1].file_id},
        city=(await state.get_data())['city']
    )

    # Запрашиваем текстовый ответ
    await message.answer(
        "Эта фотография прекрасна…",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await message.answer(
        "Я поздравляю тебя с завершением квеста! И в конце этого пути я хочу сказать, что настоящими редкими сияющими звездами являются люди, которые тебя окружают и дорожат тобой, а космосом – история, которую вы пишете вместе. Сейчас наша компания SR Space пишет историю современной российской космонавтики, перенимая лучшие традиции преемствуя путь космических достижений советского союза и дорожа каждым, кто поддерживает нас.",
        reply_markup=types.ReplyKeyboardRemove()
    )

    conn = await get_db()
    try:
        await conn.execute(
            "UPDATE users SET points = points + 30 WHERE id = $1",
            message.from_user.id
        )

        await conn.execute(
            "DELETE FROM user_progress WHERE user_id = $1",
            message.from_user.id
        )

        # Отправка отчета админам
        admins = await conn.fetch("SELECT id FROM users WHERE role = 'admin'")
        for admin in admins:
            await message.bot.send_message(
                admin['id'],
                f"🚀 Пользователь @{message.from_user.username} завершил квест!"
            )
    finally:
        await conn.close()

    from main import main_menu_kb

    await message.answer(
        "🎉 Квест завершен! Спасибо за участие!",
        reply_markup=main_menu_kb()  # Правильный вызов функции
    )
    await state.clear()
    # Создаем кнопку выхода
    builder = ReplyKeyboardBuilder()
    builder.button(text="🏠 В главное меню")

    # Сбрасываем состояние и сохраняем завершение квеста
    await state.set_state(QuestStates.QUEST_COMPLETED)
    await state.clear()  # Полная очистка состояния



# Обработчик перехода между заданиями
TASK_HANDLERS = {
    1: start_task_1,
    2: start_task_2,
    3: start_task_3,
    4: start_task_4,
    5: start_task_5,
    6: start_task_6,
    7: start_task_7,
    8: start_task_8,
    9: start_task_9,
    10: start_task_10,
}


@quest_router.callback_query(F.data.startswith("next_"))
async def handle_next(callback: types.CallbackQuery, state: FSMContext):
    try:
        current_task = int(callback.data.split("_")[1])
        next_task = current_task + 1

        # Сохраняем прогресс
        data = await state.get_data()
        conn = await get_db()
        await conn.execute(
            """INSERT INTO user_progress (user_id, current_task, city)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE 
            SET current_task = $2, city = $3""",
            callback.from_user.id, next_task, data['city']
        )

        # Вызываем следующий обработчик
        handler = TASK_HANDLERS.get(next_task)
        if handler:
            await handler(callback.message, state)
        else:
            await finish_quest(callback.message, state)

    except Exception as e:
        logger.error(f"Ошибка перехода: {e}")

# Завершение квеста
async def finish_quest(message: types.Message, state: FSMContext):
    # Начисление баллов
    conn = await get_db()
    try:
        await conn.execute(
            "UPDATE users SET points = points + 30 WHERE id = $1",
            message.from_user.id
        )

        await conn.execute(
            "DELETE FROM user_progress WHERE user_id = $1",
            message.from_user.id
        )
        # Отправка отчета админам
        admins = await conn.fetch("SELECT id FROM users WHERE role = 'admin'")
        for admin in admins:
            await message.bot.send_message(
                admin['id'],
                f"🚀 Пользователь @{message.from_user.username} завершил квест!"
            )
    finally:
        await conn.close()

    await message.answer("🎉 Квест завершен! Спасибо за участие!")
    await state.clear()

def get_exit_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="🚪 Выйти в меню")
    return builder.as_markup(resize_keyboard=True)

@quest_router.message(F.text == "🚪 Выйти в меню")
async def exit_to_menu(message: types.Message, state: FSMContext):
    # Сохраняем прогресс перед выходом
    data = await state.get_data()
    current_task = data.get('current_task', 1)
    city = data.get('city', 'unknown')

    conn = await get_db()
    try:
        await conn.execute(
            """INSERT INTO user_progress (user_id, current_task, city)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE 
            SET current_task = $2, city = $3""",
            message.from_user.id, current_task, city
        )
    finally:
        await conn.close()
    from main import main_menu_kb
    await message.answer("Прогресс сохранён! Вы можете продолжить позже.",
                         reply_markup=main_menu_kb())
    await state.clear()

async def send_admin_report(
    bot: Bot,
    user_id: int,
    task_number: int,
    answer: str = None,
    photo_id: str = None,
    city: str = None
):
    try:
        # Получаем информацию о пользователе
        conn = await get_db()
        user = await conn.fetchrow(
            "SELECT username FROM users WHERE id = $1",
            user_id
        )
        username = user['username'] if user else "Аноним"

        # Формируем текст отчета
        report_text = (
            "📊 *Новый отчет по заданию*\n"
            f"▪️ Юзер: @{username} ([{user_id}](tg://user?id={user_id}))\n"
            f"▪️ Город: {city or 'не указан'}\n"
            f"▪️ Задание: #{task_number}\n"
        )

        if answer:
            report_text += f"📝 Ответ: {answer}\n"

        # Получаем список админов
        admins = await conn.fetch(
            "SELECT id FROM users WHERE role = 'admin'"
        )

        # Отправляем каждому админу
        for admin in admins:
            try:
                if photo_id:
                    await bot.send_photo(
                        chat_id=admin['id'],
                        photo=photo_id,
                        caption=report_text,
                        parse_mode="Markdown"
                    )
                else:
                    await bot.send_message(
                        chat_id=admin['id'],
                        text=report_text,
                        parse_mode="Markdown"
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки админу {admin['id']}: {str(e)}")

    except Exception as e:
        logger.error(f"Ошибка формирования отчета: {str(e)}")
    finally:
        await conn.close()