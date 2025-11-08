import sqlite3
import logging
from datetime import datetime, date
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


# Доступные категории расходов
CATEGORIES = [
    "Еда",
    "Транспорт",
    "Кредиты",
    "ЖКХ",
    "Мобильная связь и Интернет",
    "Аптека",
    "Подписки",
    "Питомец",
    "Школа",
    "НГ",
    "АИ",
    "Ульяша",
    "Долги",
    "Стики",
    "Другое",
]

MONTH_NAMES = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


LIMIT_BREAKDOWN = {
    "Кредиты": [
        ("До 10 числа кредитка Сбер", 23749),
        ("3-го числа", 4000),
        ("20-го числа", 16900),
        ("Т 1 числа", 13000),
        ("1 числа кровать", 14000),
        ("1 декабря АльфПрест", 11000),
    ],
    "ЖКХ": [
        ("Квартплата", 8500),
        ("Электричество", 2000),
    ],
    "Мобильная связь и Интернет": [
        ("Связь и интернет", 2500),
    ],
    "Подписки": [
        ("Подписки (169+599+599+1390)", 2757),
        ("Подписки (дополнительно)", 2500),
    ],
    "Питомец": [
        ("Корм", 4500),
        ("Груминг", 2000),
    ],
    "Аптека": [
        ("Аптека", 3000),
        ("Аптека (дополнительно)", 1000),
    ],
    "Школа": [
        ("Школа", 2000),
        ("Школа (дополнительно)", 11000),
    ],
    "НГ": [
        ("План на НГ", 25000),
    ],
    "АИ": [
        ("План на АИ", 25000),
    ],
    "Ульяша": [
        ("Ульяша", 20000),
    ],
    "Стики": [
        ("Стики", 16000),
    ],
}


# Кнопки главного меню
BTN_ADD = "➕ Добавить расход"
BTN_SALARY = "💼 Установить зарплату"
BTN_LIMIT = "🎯 Лимит по категории"
BTN_LIMIT_DETAILS = "🧾 Детали лимитов"
BTN_STATS = "📊 Статистика"
BTN_STATS_CURRENT = "📈 Текущий месяц"
BTN_STATS_PREVIOUS = "📉 Прошлый месяц"
BTN_STATS_YEAR = "🗓️ Год"
BTN_STATS_CATEGORY = "📂 Детали по категории"
BTN_STATS_BACK = "⬅️ Главное меню"
BTN_CLEAR = "🧹 Очистить расходы"
BTN_HELP = "ℹ️ Помощь"


# Инициализация БД
def init_db():
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS salaries (
            user_id INTEGER PRIMARY KEY,
            amount INTEGER NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS salary_history (
            user_id INTEGER NOT NULL,
            effective_date TEXT NOT NULL,
            amount INTEGER NOT NULL,
            PRIMARY KEY (user_id, effective_date)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS category_limits (
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount INTEGER NOT NULL,
            PRIMARY KEY (user_id, category)
        )
    ''')
    conn.commit()
    conn.close()


# Сохранение расхода
def add_expense(user_id, amount, category, description):
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO expenses (user_id, amount, category, description, date)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, int(amount), category, description, datetime.now().isoformat()))
    conn.commit()
    conn.close()


# Получение статистики в заданном диапазоне дат (агрегированные по всем пользователям)
def get_stats(start_date=None, end_date=None):
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()

    base_query = 'SELECT SUM(amount) FROM expenses WHERE 1=1'
    params = []
    if start_date is not None:
        base_query += ' AND date >= ?'
        params.append(start_date)
    if end_date is not None:
        base_query += ' AND date < ?'
        params.append(end_date)

    cursor.execute(base_query, params)
    total_raw = cursor.fetchone()[0]
    total = int(total_raw) if total_raw is not None else 0

    category_query = '''
        SELECT category, SUM(amount)
        FROM expenses
        WHERE 1=1
    '''
    category_params = []
    if start_date is not None:
        category_query += ' AND date >= ?'
        category_params.append(start_date)
    if end_date is not None:
        category_query += ' AND date < ?'
        category_params.append(end_date)
    category_query += ' GROUP BY category'

    cursor.execute(category_query, category_params)
    categories_data = cursor.fetchall()

    conn.close()
    categories = {category: int(amount) for category, amount in categories_data}
    return total, categories


def set_salary(user_id, amount):
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO salaries (user_id, amount)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET amount = excluded.amount
        ''',
        (user_id, int(amount)),
    )
    conn.commit()
    conn.close()
    record_salary_history(user_id, amount)


def get_category_limits():
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    cursor.execute('SELECT category, SUM(amount) FROM category_limits GROUP BY category')
    rows = cursor.fetchall()
    conn.close()
    return {category: int(amount) for category, amount in rows}


def set_category_limit(user_id, category, amount):
    amount = int(amount)
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    if amount <= 0:
        cursor.execute('DELETE FROM category_limits WHERE user_id = ? AND category = ?', (user_id, category))
    else:
        cursor.execute(
            '''
            INSERT INTO category_limits (user_id, category, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, category) DO UPDATE SET amount = excluded.amount
            ''',
            (user_id, category, amount),
        )
    conn.commit()
    conn.close()


def clear_expenses(user_id):
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM expenses WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()


def advance_month(year, month):
    if month == 12:
        return year + 1, 1
    return year, month + 1


def retreat_month(year, month):
    if month == 1:
        return year - 1, 12
    return year, month - 1


def month_range(year, month):
    start = datetime(year, month, 1)
    next_year, next_month = advance_month(year, month)
    end = datetime(next_year, next_month, 1)
    return start.isoformat(), end.isoformat()


def format_month_year(year, month):
    name = MONTH_NAMES.get(month, str(month))
    return f"{name} {year}"


def record_salary_history(user_id, amount, target_date=None):
    if target_date is None:
        target_date = date.today()
    first_day = target_date.replace(day=1)
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO salary_history (user_id, effective_date, amount)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, effective_date) DO UPDATE SET amount = excluded.amount
        ''',
        (user_id, first_day.isoformat(), int(amount)),
    )
    conn.commit()
    conn.close()


def get_total_salary_for_month(year, month):
    next_year, next_month = advance_month(year, month)
    threshold = date(next_year, next_month, 1).isoformat()

    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT sh.user_id, sh.amount
        FROM salary_history sh
        JOIN (
            SELECT user_id, MAX(effective_date) AS last_date
            FROM salary_history
            WHERE effective_date < ?
            GROUP BY user_id
        ) latest
        ON latest.user_id = sh.user_id AND latest.last_date = sh.effective_date
        ''',
        (threshold,),
    )
    rows = cursor.fetchall()
    salary_map = {user_id: int(amount) for user_id, amount in rows}

    cursor.execute('SELECT user_id, amount FROM salaries')
    for user_id, amount in cursor.fetchall():
        salary_map.setdefault(user_id, int(amount))

    conn.close()

    return sum(salary_map.values())


def get_expense_details_for_category(category, start_date=None, end_date=None):
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    query = 'SELECT date, amount, COALESCE(description, "") FROM expenses WHERE category = ?'
    params = [category]
    if start_date is not None:
        query += ' AND date >= ?'
        params.append(start_date)
    if end_date is not None:
        query += ' AND date < ?'
        params.append(end_date)
    query += ' ORDER BY date'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    details = []
    for raw_date, amount, description in rows:
        try:
            parsed_date = datetime.fromisoformat(raw_date)
        except ValueError:
            parsed_date = datetime.fromisoformat(raw_date.replace(' ', 'T', 1))
        details.append((parsed_date, int(amount), description.strip()))
    return details


def get_months_in_year(year):
    today = date.today()
    if year < today.year:
        return list(range(1, 13))
    if year > today.year:
        return []
    return list(range(1, today.month + 1))


def create_category_keyboard():
    rows = []
    current_row = []
    for category in CATEGORIES:
        current_row.append(KeyboardButton(category))
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def create_main_keyboard():
    rows = [
        [KeyboardButton(BTN_ADD), KeyboardButton(BTN_STATS_CURRENT)],
        [KeyboardButton(BTN_STATS), KeyboardButton(BTN_LIMIT)],
        [KeyboardButton(BTN_SALARY), KeyboardButton(BTN_LIMIT_DETAILS)],
        [KeyboardButton(BTN_CLEAR), KeyboardButton(BTN_HELP)],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def create_stats_keyboard():
    rows = [
        [KeyboardButton(BTN_STATS_PREVIOUS)],
        [KeyboardButton(BTN_STATS_YEAR)],
        [KeyboardButton(BTN_STATS_CATEGORY)],
        [KeyboardButton(BTN_STATS_BACK)],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def reset_state(user_data):
    user_data.pop('state', None)
    user_data.pop('pending_expense', None)
    user_data.pop('pending_limit', None)


def previous_month_date(reference=None):
    if reference is None:
        reference = date.today()
    year, month = retreat_month(reference.year, reference.month)
    return date(year, month, 1)


def build_month_stats_message(target_date=None):
    if target_date is None:
        target_date = date.today()
    year = target_date.year
    month = target_date.month
    start, end = month_range(year, month)

    total, categories = get_stats(start, end)
    limits = get_category_limits()
    salary = get_total_salary_for_month(year, month)

    title = format_month_year(year, month)
    message = f"Статистика за {title}:\n\n"
    message += f"Всего потрачено: {total} ₽\n"

    if salary:
        remaining = salary - total
        message += f"Заработная плата: {salary} ₽\n"
        message += f"Остаток: {remaining} ₽\n\n"
    else:
        message += "Заработная плата не установлена для этого периода. Используйте кнопку \""
        message += f"{BTN_SALARY}\".\n\n"

    message += "По категориям:\n"

    for category in CATEGORIES:
        spent = categories.get(category, 0) or 0
        limit = limits.get(category)
        if limit is not None:
            diff = limit - spent
            if diff >= 0:
                message += (
                    f"  {category}: {spent} ₽ / лимит {limit} ₽ / 🟢 Остаток: {diff} ₽\n"
                )
            else:
                message += (
                    f"  {category}: {spent} ₽ / лимит {limit} ₽ / 🔴 Превышение: {abs(diff)} ₽\n"
                )
        else:
            message += f"  {category}: {spent} ₽\n"

    extra_categories = {cat: amt for cat, amt in categories.items() if cat not in CATEGORIES}
    for category, spent in extra_categories.items():
        message += f"  {category}: {spent} ₽\n"

    return message


def build_year_stats_message(year=None):
    if year is None:
        year = date.today().year

    months = get_months_in_year(year)
    if not months:
        return "Для указанного года статистика недоступна."

    start = datetime(year, 1, 1).isoformat()
    if year < date.today().year:
        end = datetime(year + 1, 1, 1).isoformat()
    else:
        next_year, next_month = advance_month(date.today().year, date.today().month)
        end = datetime(next_year, next_month, 1).isoformat()

    total, categories = get_stats(start, end)
    limits = get_category_limits()

    salary_sum = 0
    for month in months:
        salary_value = get_total_salary_for_month(year, month)
        salary_sum += salary_value

    months_count = len(months)
    remaining = salary_sum - total

    message = f"Годовая статистика за {year} год:\n\n"
    message += f"Месяцев в расчёте: {months_count}\n"
    message += f"Сумма зарплаты: {salary_sum} ₽\n"
    message += f"Сумма расходов: {total} ₽\n"
    message += f"Остаток: {remaining} ₽\n\n"
    message += "По категориям:\n"

    for category in CATEGORIES:
        spent = categories.get(category, 0) or 0
        limit = limits.get(category)
        if limit is not None:
            diff = limit - spent
            if diff >= 0:
                message += f"  {category}: {spent} ₽ / лимит {limit} ₽ / 🟢 Остаток: {diff} ₽\n"
            else:
                message += f"  {category}: {spent} ₽ / лимит {limit} ₽ / 🔴 Превышение: {abs(diff)} ₽\n"
        else:
            message += f"  {category}: {spent} ₽\n"

    extra_categories = {cat: amt for cat, amt in categories.items() if cat not in CATEGORIES}
    for category, spent in extra_categories.items():
        message += f"  {category}: {spent} ₽\n"

    if any(limits.values()):
        message += "\nНапоминаем: лимиты задаются помесячно и не учитываются в годовом сравнении."

    return message


def build_category_details_message(category, target_date=None):
    if target_date is None:
        target_date = date.today()
    year = target_date.year
    month = target_date.month
    start, end = month_range(year, month)

    details = get_expense_details_for_category(category, start, end)
    total_spent = sum(amount for _, amount, _ in details)
    limit = get_category_limits().get(category)
    title = format_month_year(year, month)

    message_lines = [
        f"Детализация категории '{category}' за {title}",
        "",
        f"Потрачено: {total_spent} ₽",
    ]

    if limit is not None:
        diff = limit - total_spent
        if diff >= 0:
            message_lines.append(f"Лимит: {limit} ₽\nОстаток: 🟢 {diff} ₽")
        else:
            message_lines.append(f"Лимит: {limit} ₽\nПревышение: 🔴 {abs(diff)} ₽")
    else:
        message_lines.append("Лимит не задан.")

    message_lines.append("")

    if details:
        message_lines.append("Расходы:")
        for entry_date, amount, description in details:
            date_str = entry_date.strftime('%d.%m.%Y %H:%M')
            desc = description if description else "Без описания"
            message_lines.append(f"  • {date_str} — {amount} ₽ — {desc}")
    else:
        message_lines.append("Расходов в этой категории за период нет.")

    return "\n".join(message_lines)


def build_limit_details_message():
    lines = ["Детализация лимитов по категориям:\n"]
    for category, items in LIMIT_BREAKDOWN.items():
        total = sum(amount for _, amount in items)
        lines.append(f"{category}: {total} ₽")
        for description, amount in items:
            lines.append(f"  - {description}: {amount} ₽")
        lines.append("")

    missing = [cat for cat in CATEGORIES if cat not in LIMIT_BREAKDOWN]
    if missing:
        lines.append("Нет детальной информации для категорий:")
        for category in missing:
            lines.append(f"  - {category}")

    return "\n".join(line.rstrip() for line in lines).strip()


async def send_current_month_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = build_month_stats_message(date.today())
    await update.message.reply_text(message, reply_markup=create_main_keyboard())


async def send_previous_month_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = previous_month_date()
    message = build_month_stats_message(target)
    await update.message.reply_text(message, reply_markup=create_main_keyboard())


async def send_year_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = build_year_stats_message(date.today().year)
    await update.message.reply_text(message, reply_markup=create_main_keyboard())


async def send_limit_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = build_limit_details_message()
    await update.message.reply_text(message, reply_markup=create_main_keyboard())


# Команды бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = create_main_keyboard()
    await update.message.reply_text(
        "Привет! Я бот для учёта расходов.\n"
        "Используйте кнопки ниже или команды:",
        reply_markup=reply_markup
    )


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_state(context.user_data)
    context.user_data['state'] = 'awaiting_amount'
    context.user_data['pending_expense'] = {}
    await update.message.reply_text(
        "Введите сумму расхода:",
        reply_markup=ReplyKeyboardRemove(),
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    state = context.user_data.get('state')

    if state is None:
        if text == BTN_ADD:
            await add(update, context)
            return
        if text == BTN_STATS_CURRENT:
            await send_current_month_stats(update, context)
            return
        if text == BTN_SALARY:
            await salary(update, context)
            return
        if text == BTN_LIMIT:
            await limit_command(update, context)
            return
        if text == BTN_STATS:
            reset_state(context.user_data)
            context.user_data['state'] = 'awaiting_stats_option'
            await update.message.reply_text(
                "Выберите интересующий отчёт:",
                reply_markup=create_stats_keyboard(),
            )
            return
        if text == BTN_LIMIT_DETAILS:
            await send_limit_details(update, context)
            return
        if text == BTN_CLEAR:
            await clear_command(update, context)
            return
        if text == BTN_HELP:
            await help_command(update, context)
            return

    if state == 'awaiting_salary':
        normalized = text.replace(' ', '')
        if normalized.startswith('+'):
            normalized = normalized[1:]
        try:
            amount = int(normalized)
        except ValueError:
            await update.message.reply_text("Сумма должна быть целым числом, попробуйте ещё раз.")
            return

        if amount <= 0:
            await update.message.reply_text("Сумма должна быть положительной")
            return

        set_salary(user_id, amount)
        reset_state(context.user_data)
        await update.message.reply_text(f"Заработная плата установлена: {amount} ₽")
        stats_message = build_month_stats_message(date.today())
        await update.message.reply_text(stats_message, reply_markup=create_main_keyboard())
        return

    if state == 'awaiting_amount':
        normalized = text.replace(' ', '')
        if normalized.startswith('+'):
            normalized = normalized[1:]
        try:
            amount = int(normalized)
        except ValueError:
            await update.message.reply_text("Сумма должна быть целым числом, попробуйте ещё раз.")
            return

        if amount <= 0:
            await update.message.reply_text("Сумма должна быть больше нуля.")
            return

        context.user_data.setdefault('pending_expense', {})['amount'] = amount
        context.user_data['state'] = 'awaiting_category'
        await update.message.reply_text(
            "Выберите категорию:",
            reply_markup=create_category_keyboard(),
        )
        return

    if state == 'awaiting_category':
        if text not in CATEGORIES:
            await update.message.reply_text(
                "Выберите категорию из списка на клавиатуре.",
                reply_markup=create_category_keyboard(),
            )
            return

        context.user_data.setdefault('pending_expense', {})['category'] = text
        context.user_data['state'] = 'awaiting_description'
        await update.message.reply_text(
            "Введите описание расхода (или '-' если без описания):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if state == 'awaiting_description':
        description = '' if text == '-' else text
        pending = context.user_data.get('pending_expense', {})
        amount = pending.get('amount')
        category = pending.get('category')

        if amount is None or category is None:
            reset_state(context.user_data)
            await update.message.reply_text("Не удалось сохранить расход, попробуйте снова команду /add.")
            return

        add_expense(user_id, amount, category, description)
        reset_state(context.user_data)
        await update.message.reply_text(f"Расход добавлен: {amount} ₽ ({category})")
        stats_message = build_month_stats_message(date.today())
        await update.message.reply_text(stats_message, reply_markup=create_main_keyboard())
        return

    if state == 'awaiting_limit_category':
        if text not in CATEGORIES:
            await update.message.reply_text(
                "Выберите категорию из списка на клавиатуре.",
                reply_markup=create_category_keyboard(),
            )
            return

        context.user_data['pending_limit'] = {'category': text}
        context.user_data['state'] = 'awaiting_limit_value'
        await update.message.reply_text(
            "Введите лимит для категории (0 — чтобы удалить лимит):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if state == 'awaiting_stats_option':
        if text == BTN_STATS_PREVIOUS:
            reset_state(context.user_data)
            await send_previous_month_stats(update, context)
            return
        if text == BTN_STATS_YEAR:
            reset_state(context.user_data)
            await send_year_stats(update, context)
            return
        if text == BTN_STATS_CATEGORY:
            context.user_data['state'] = 'awaiting_detail_category'
            await update.message.reply_text(
                "Выберите категорию для детальной статистики:",
                reply_markup=create_category_keyboard(),
            )
            return
        if text == BTN_STATS_BACK:
            reset_state(context.user_data)
            await update.message.reply_text(
                "Возврат в главное меню.", reply_markup=create_main_keyboard()
            )
            return

        await update.message.reply_text(
            "Выберите вариант из меню статистики.",
            reply_markup=create_stats_keyboard(),
        )
        return

    if state == 'awaiting_detail_category':
        if text not in CATEGORIES:
            await update.message.reply_text(
                "Выберите категорию из списка на клавиатуре.",
                reply_markup=create_category_keyboard(),
            )
            return

        reset_state(context.user_data)
        message = build_category_details_message(text, date.today())
        await update.message.reply_text(message, reply_markup=create_main_keyboard())
        return

    if state == 'awaiting_limit_value':
        normalized = text.replace(' ', '')
        if normalized.startswith('+'):
            normalized = normalized[1:]
        try:
            limit_value = int(normalized)
        except ValueError:
            await update.message.reply_text("Лимит должен быть целым числом, попробуйте ещё раз.")
            return

        if limit_value < 0:
            await update.message.reply_text("Лимит не может быть отрицательным. Введите 0 для удаления или положительное число.")
            return

        pending_limit = context.user_data.get('pending_limit', {})
        category = pending_limit.get('category')

        if category is None:
            reset_state(context.user_data)
            await update.message.reply_text("Не удалось сохранить лимит, попробуйте снова команду /limit.")
            return

        set_category_limit(user_id, category, limit_value)
        reset_state(context.user_data)

        if limit_value == 0:
            await update.message.reply_text(f"Лимит для категории '{category}' удалён.")
        else:
            await update.message.reply_text(f"Лимит для категории '{category}' установлен: {limit_value} ₽")

        stats_message = build_month_stats_message(date.today())
        await update.message.reply_text(stats_message, reply_markup=create_main_keyboard())
        return

    await update.message.reply_text(
        "Я вас не понял. Используйте кнопки главного меню или команду /help для справки.",
        reply_markup=create_main_keyboard(),
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_state(context.user_data)
    context.user_data['state'] = 'awaiting_stats_option'
    await update.message.reply_text(
        "Выберите интересующий отчёт:",
        reply_markup=create_stats_keyboard(),
    )


async def salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if not context.args:
        reset_state(context.user_data)
        context.user_data['state'] = 'awaiting_salary'
        await update.message.reply_text(
            "Введите сумму заработной платы:",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    normalized = context.args[0].replace(' ', '')
    if normalized.startswith('+'):
        normalized = normalized[1:]
    try:
        amount = int(normalized)
    except ValueError:
        await update.message.reply_text("Сумма должна быть целым числом!")
        return

    if amount <= 0:
        await update.message.reply_text("Сумма должна быть положительной")
        return

    set_salary(user_id, amount)
    await update.message.reply_text(f"Заработная плата установлена: {amount} ₽")
    stats_message = build_month_stats_message(date.today())
    await update.message.reply_text(stats_message, reply_markup=create_main_keyboard())


async def limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_state(context.user_data)
    context.user_data['state'] = 'awaiting_limit_category'
    await update.message.reply_text(
        "Выберите категорию для установки лимита:",
        reply_markup=create_category_keyboard(),
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    reset_state(context.user_data)
    clear_expenses(user_id)
    await update.message.reply_text("Вся история расходов очищена.")
    stats_message = build_month_stats_message(date.today())
    await update.message.reply_text(stats_message, reply_markup=create_main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные действия:\n"
        f"{BTN_ADD} — пошаговое добавление расхода\n"
        f"{BTN_STATS_CURRENT} — статистика за текущий месяц\n"
        f"{BTN_SALARY} — установка суммы зарплаты\n"
        f"{BTN_LIMIT} — настройка лимитов по категориям\n"
        f"{BTN_STATS} — выбор отчётов (прошлый месяц, год, детально по категории)\n"
        f"{BTN_LIMIT_DETAILS} — из чего складываются лимиты\n"
        f"{BTN_CLEAR} — очистка истории расходов\n"
        f"{BTN_HELP} — эта подсказка\n\n"
        "Используйте кнопки главного меню или команды /add, /salary, /limit, /clear, /stats.\n"
        "Все суммы вводите целыми числами.",
        reply_markup=create_main_keyboard(),
    )


def main():
    # Ваш токен от @BotFather
    TOKEN = "8570230495:AAHkfsBNE2EtF8rq--YM9DoBJG2SmDgFbbw"

    init_db()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add))
    application.add_handler(CommandHandler("salary", salary))
    application.add_handler(CommandHandler("limit", limit_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()


if __name__ == '__main__':
    main()
