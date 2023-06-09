import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils import executor
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import aiogram.utils.markdown as md
from aiogram.types import ParseMode
from queue_database import database as db
from queue_database.database import *
from formatted import *
from simulator import *
from functional import *
import threading
import asyncio

db = db_path

logging.basicConfig(level=logging.INFO)
API_TOKEN = "6289556666:AAGpinAWZMv3AaI3pNOk4s79_pFLP3jpV0E"

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

class Form(StatesGroup):
    name = State()
    age = State()
    gender = State()
    priority = State()
    allowed_waiting_time = State()
    suspend = State()

priority_level_dict = {'низкий':1,'средний':2,'высокий':3, }
inv_priority_level_dict = {v: k for k, v in priority_level_dict.items()}

@dp.message_handler(commands=["start", "help"])
async def start_command(message: types.Message):
    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    reg = types.KeyboardButton("Регистрация")
    queue = types.KeyboardButton("Просмотр очереди")
    update = types.KeyboardButton("Обновление параметров")
    menu.add(reg, queue)
    menu.add(update)
    await message.reply("Привет! Я бот для огрганизации очереди. Выберите вариант:", reply=False, reply_markup=menu)

@dp.message_handler(lambda message: message.text == "Регистрация")
async def process_button1(message: types.Message):
    user_id = message.chat.id
    if not await is_id_unique('customers', user_id):  # Check if the user is already registered
        await bot.send_message(user_id, "Вы не можете пройти регистрацию дважды")
        # Send the user's current position in the queue
        # position = await get_queue_position(user_id)  # Assuming you have a function to get a user's position
        # await bot.send_message(user_id, f"Your current position in the queue is {position}.")
        return  # Exit the function if the user is already registered

    await message.reply("Напишите своё имя", reply=False, reply_markup=types.ReplyKeyboardRemove())
    await Form.name.set()

@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['name'] = message.text
    await Form.next()
    await message.reply("Какой у вас возраст?")

@dp.message_handler(lambda message: not message.text.isdigit(), state=Form.age)
async def process_age_invalid(message: types.Message):
    return await message.reply("Нужно ввести число.\nКакой у вас возраст?")

@dp.message_handler(lambda message: message.text.isdigit(), state=Form.age)
async def process_age(message: types.Message, state: FSMContext):
    # Update state and data
    await Form.next()
    await state.update_data(age=int(message.text))

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add("М", "Ж")

    await message.reply("Ваш пол?", reply_markup=markup)

@dp.message_handler(lambda message: message.text not in ["М", "Ж"], state=Form.gender)
async def process_gender_invalid(message: types.Message):
    return await message.reply("Мы поддерживаем только два пола в данный момент. Выберите пол из клавиатуры.")

@dp.message_handler(state=Form.gender)
async def process_gender(message: types.Message, state: FSMContext):
    await Form.next()
    async with state.proxy() as data:
        data['gender'] = message.text

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)
    markup.add("низкий", "средний", "высокий")

    await message.reply("Как бы вы оценили ваш уровень спешки?", reply_markup=markup)

@dp.message_handler(lambda message: message.text not in ["низкий", "средний", "высокий"], state=Form.priority)
async def process_priority_invalid(message: types.Message):
    return await message.reply("Мы поддерживаем только предложенные уровни спешки в данный момент\n"
                               "Выберите другой уровень из клавиатуры.")

@dp.message_handler(state=Form.priority)
async def process_priority(message: types.Message, state: FSMContext):

    async with state.proxy() as data:
        data['priority'] = priority_level_dict[message.text]

    await Form.next()
    await message.reply("Сколько времени вы готовы ждать?(в минутах)", reply=False, reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(lambda message: not message.text.isdigit(), state=Form.allowed_waiting_time)
async def process_allowed_waiting_time_invalid(message: types.Message):
    return await message.reply("Нужно ввести число.\n"
                               "Сколько времени вы готовы ждать?(в минутах)")

@dp.message_handler(lambda message: message.text.isdigit(), state=Form.allowed_waiting_time)
async def process_allowed_waiting_time(message: types.Message, state: FSMContext):
    # Update state and data
    # await state.update_data(age=int(message.text))
    async with state.proxy() as data:
        data['allowed_waiting_time'] = message.text

        cl = Client(chat_id=message.chat.id,
                    name=data['name'],
                    age=data['age'],
                    gender=data['gender'],
                    priority=data['priority'],
                    allowed_waiting_time=data['allowed_waiting_time'],)

        await bot.send_message(
                    cl.chat_id,
                    md.text(
                        md.text('Вы записаны в очередь, ', md.bold(cl.name), '!'),
                        md.text('Возраст:', md.code(cl.age)),
                        md.text('Пол:', cl.gender),
                        md.text('Уровень спешки:', inv_priority_level_dict[cl.priority]),
                        md.text('Готовы ожидать:', cl.allowed_waiting_time, ' мин'),
                        md.text('Время регистрации:', cl.time_arrive),
                        sep='\n',
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
        clients[cl.chat_id] = cl
        await insert(cl)

    await state.finish()

@dp.message_handler(lambda message: message.text == "Просмотр очереди")
async def process_button2(message: types.Message):
    queue_list = await customer_query(True, 'name', 'time_arrive')
    # logic of transforming by algorithm
    # queue_list is the first state, then we need to apply some logic on sorting, then transform by relaxation param
    ext = EXTimings()
    ext.fill_exams()
    db_slice = await customer_query(sort_dttm=True)
    arr = ext.original_order(db_slice)

    await bot.send_message(message.chat.id,md.text(
        md.text('\nOriginal order:\n', queue_format(queue_list)),
        md.text('\nModified order:\n', queue_format(arr)),
        sep='\n',)
    )

@dp.message_handler(lambda message: message.text == "Обновление параметров")
async def process_button3(message: types.Message):
    update_menu = types.ReplyKeyboardMarkup(resize_keyboard=True, selective=True)

    btns = [KeyboardButton("Я хочу уйти, не дожидаясь своей очереди"),
            KeyboardButton("Я хочу прийти через n минут"),
            ]

    for item in btns:
        update_menu.add(item)

    await message.reply(
        "Выберите параметры обновления",
        reply_markup=update_menu,
    )

@dp.message_handler(lambda message: message.text == "Я хочу уйти, не дожидаясь своей очереди")
async def process_button4(message: types.Message):
    user_id = message.chat.id
    if not await db.is_id_unique('customers', user_id):
        await bot.send_message(user_id, 'Вы не можете уйти из очереди без регистрации в ней.')
        return
    await db.update(user_id, premature_departure=True)
    await message.reply(
        md.text("Вы исключены из очереди"),
        reply=False,
    )

@dp.message_handler(lambda message: message.text == "Я хочу прийти через n минут")
async def process_button5(message: types.Message):
    user_id = message.chat.id
    if not await db.is_id_unique('customers', user_id):
        await bot.send_message(user_id, 'Вы не можете обновить настройки без регистрации в очереди.')
        return
    await Form.suspend.set()
    return await message.reply("Через какое время вы вернетесь?(в минутах)")

@dp.message_handler(lambda message: not message.text.isdigit(), state=Form.suspend)
async def process_suspend_invalid(message: types.Message):
    return await message.reply("Нужно ввести число.\nЧерез какое время вы вернетесь?(в минутах)")

@dp.message_handler(lambda message: message.text.isdigit(), state=Form.suspend)
async def process_suspend(message: types.Message):
    # Update state and data
    await Form.next()
    await update(message.chat.id, leave_time=int(message.text))
    await bot.send_message(message.chat.id,
        md.text(f"Обновлены параметры записи:\nВы отойдёте на {message.text} минут"))

def start_polling_with_new_event_loop(dp):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    executor.start_polling(dp, skip_updates=True)

# if __name__ == "__main__":
#     logging.info("Starting bot...")
#     create_tables()
#     ext = EXTimings()
#     asyncio.run(ext.initialize())
#     polling_thread = threading.Thread(target=start_polling_with_new_event_loop, args=(dp,))
#     polling_thread.start()
#     polling_thread.join()  # Wait for the thread to finish
#     ext.stop()

if __name__ == "__main__":
    logging.info("Starting bot...")
    create_tables()
    loop = asyncio.get_event_loop()
    ext = EXTimings()
    loop.create_task(ext.initialize())
    loop.create_task(test_loop())
    polling_thread = threading.Thread(target=start_polling_with_new_event_loop, args=(dp,))
    polling_thread.start()
    polling_thread.join()
    ext.stop()


# 1. добавить в клавиатуру возможность вернуться в главное меню после прохода в другие пункты
# 2. также убрать клавиатуру после регистрации чтобы просмотреть текущую очередь или ливнуть из очереди
# 3. добавить возможность отменить регистрацию при прохождении регистрации
# 7. modified order в боте не робит что-то, там нет пользователя который только добавился (если бд уже создана, т.е. регистрация идет не для первого чела в очереди), в другом случае еще не проверяла
# бд заполняется пользователями при запуске бота


# todo: после получения бд переделать сортировки. добавить функцию которая по спешке а внутри спешки по времени записи
# todo: функцию которая добавляет отсортированные записи по спешке времени из буферного файла в свои категории спешки
# это значит что есть таблица которая отсортирована алгом и таблица новых по спешке времени (дальше на записи)
# то есть берем формально (не скль таблицу) а типа отделяем лист и делим на 2 части с уровнем спешки 3 и все что ниже
# в этот уровень спешки 3 соединяем в конец append элемент 1й из. короче 3йки падать в конец 3, 2йки в конец 2к
# и должны делать это по очереди пока есть какой-то буфер
#
# мы должны организовать. у нас есть бд мы из нее взяли данне в класс и в этом классе мы пытались сделать сортировку и в этот момент какая-то запись
# долетела в базу, мы ее забрали к нам и ее нужно  добавить к алгоритму чтобы она сортировалась, могло прилететь 1 или несколько записей
# чтобы добавить ее к сортировке нам бы хорошо ее добавить - влить и отсортировать по уровню спешки
# но тогда у нас собьется предыдущая сортировка нашего алгоритма и мы так делать не можем
# поэтому мы должны буферный файл достать - это уже сделано
# только надо не только по времени сортировать а по спешке и времени
# и дальше мы идем на первую запись этого буферного файла и допустим она там с таким-то уровнем спешки и мы ее к такому же уровню спешки
# должны добавить но в конец
# проще всего (но можно как угодно) чтобы добавиьт в конец троечку к троечке (3 самый выскокий уровень в системе)
# взять элементы которые содержат 3ку и разъединить список в том месте (типа засунуть - разъединить. нужна отдельная функция. которая будет добавлять
# в правильное место элемент относительно его спешки. т.е. функция должна разъединять лист и туда закидывать)
#
# берем формально отделяем лист и делим его на 2 части
# с уровнем спешки 3
# и все что ниже
# в этот уровень спешки 3 снизу присоединяем
#
#
# todo: в сортировке в самом боте (когда он отправляет сообщение с текущей очередью) - при добавлении нового пользователя кто-то из уже существующих не отображается. как будто там при отображении фиксированное количество записей из тестового датасета - 19