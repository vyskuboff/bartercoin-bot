import re
import math
import asyncio
from decimal import Decimal
import requests
from database import DatabaseManager
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, KeyboardButton, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters
)
from translations import get_translation
from config import AUTHORIZED_USER_ID, MILITCORP_GROUP_ID, TOKENTG_MILITCORP_BOT
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AUTHORIZED_ADMINS = AUTHORIZED_USER_ID

default_language_code = 'en'

class TelegramBot:

    def __init__(self, TOKEN: str, db: DatabaseManager):
        self._db = db
        self.application = Application.builder().token(TOKEN).build()

    async def actions_command(self, update: Update, context: CallbackContext) -> None:
        user_id = update.message.chat.id
        user_lang = self._db.get_user_language(user_id) or default_language_code
        balance_text = get_translation(user_lang, 'button_balance')
        send_text = get_translation(user_lang, 'button_send')
        stats_text = get_translation(user_lang, 'button_stats')
        actions_message_text = get_translation(user_lang, 'send_op_markup')

        buttons = [
            [
                InlineKeyboardButton(balance_text, callback_data="balance"),
                InlineKeyboardButton(send_text, callback_data="send"),
            ]
        ]

        if user_id in AUTHORIZED_ADMINS:
            buttons.append([InlineKeyboardButton(stats_text, callback_data='get_stats')])

        localized_op_markup = InlineKeyboardMarkup(buttons)

        await update.message.reply_text(actions_message_text, reply_markup=localized_op_markup)

    def send_admin_notification(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{TOKENTG_MILITCORP_BOT}/sendMessage"
        payload = {
            "chat_id": MILITCORP_GROUP_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            logger.error(f"Failed to send message: {response.status_code} - {response.text}")


    # Command handler for /start command
    async def start(self, update: Update, context: CallbackContext) -> None:
        user_id = update.message.chat.id
        phone = self._db.get_assoc(user_id)
        user = update.message.from_user
        
        # Определение языка пользователя, если он зарегистрирован, иначе использование языка по умолчанию
        user_lang = self._db.get_user_language(user_id) if phone else default_language_code

        # Получение локализованных текстов
        send_phone_text = get_translation(user_lang, 'send_phone_button')
        already_auth_text = get_translation(user_lang, 'already_authorized')
        request_phone_text = get_translation(user_lang, 'request_phone')

        # Создание локализованной клавиатуры
        markup = ReplyKeyboardMarkup(
            [[KeyboardButton(send_phone_text, request_contact=True)]],
            one_time_keyboard=True,
        )

        if phone:
            await update.message.reply_text(already_auth_text)
        else:
            await update.message.reply_text(request_phone_text, reply_markup=markup)

    # Message handler for receiving phone number
    async def phone_auth(self, update: Update, context: CallbackContext) -> None:
        user_id = update.message.chat.id
        user_lang = self._db.get_user_language(user_id) or default_language_code
        user = update.message.from_user

        if update.message.contact:
            # Функция для очистки номера телефона
            def clean_phone(phone_number):
                match = re.findall(r'\d', phone_number)
                cleaned_number = '+' + ''.join(match)
                return cleaned_number

            phone_number = clean_phone(update.message.contact.phone_number)
            contact_id = update.message.contact.user_id

            # Переменные для локализации текста
            unclear_context_text = get_translation(user_lang, 'unclear_context')
            not_your_contact_text = get_translation(user_lang, 'not_your_contact')
            number_linked_text = get_translation(user_lang, 'number_linked', phone_number=phone_number)
            balance_text = get_translation(user_lang, 'button_balance')
            send_text = get_translation(user_lang, 'button_send')
            phone_auth_message_text = get_translation(user_lang, 'send_op_markup')

            localized_op_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(balance_text, callback_data="balance"),
                        InlineKeyboardButton(send_text, callback_data="send"),
                    ]
                ]
            )

            phone = self._db.get_assoc(user_id)

            if phone:
                await update.message.reply_text(unclear_context_text, reply_markup=localized_op_markup)
            elif not contact_id == user_id:
                await update.message.reply_text(not_your_contact_text, reply_markup=localized_op_markup)
            else:
                # Store the user in the database
                self._db.add_assoc(user_id, phone_number)

                if not self._db.get_user(phone_number):
                    self._db.add_user(phone_number)

                await update.message.reply_text(number_linked_text, reply_markup=ReplyKeyboardRemove())
                await update.message.reply_text(phone_auth_message_text, reply_markup=localized_op_markup)
                # Send notification to admin group
                notification_message = (
                    f"User provided phone number(новый юзер предоставил свой тел):\n"
                    f"ID: `{user.id}`\n"
                    f"Name(имя в ТГ): `{user.full_name}`\n"
                    f"Username: `{user.username}`\n"
					f"Language(Язык юзера в ТГ): `{user.language_code}`\n"
                    f"Phone(предоставленный тел): `{phone_number}`"
                )
                self.send_admin_notification(notification_message)
        else:
            # Если контактные данные отсутствуют, отправляем сообщение об ошибке
            error_text = get_translation(user_lang, 'unauthorized_key')
            await update.message.reply_text(error_text) 

    # 'balance' and 'send' handler
    async def keyboard_handler(self, update: Update, context: CallbackContext) -> None:
        query = update.callback_query
        user_id = query.from_user.id
        button_data = query.data
        user_lang = self._db.get_user_language(user_id) or default_language_code

        unauthorized_text = get_translation(user_lang, 'unauthorized_key')
        enter_phone_text = get_translation(user_lang, 'input_send_phone')
        unknown_command_text = get_translation(user_lang, 'non_comand')
        phone = self._db.get_assoc(user_id)
        if not phone:
            await query.message.reply_text(unauthorized_text)
            await query.answer()
            return

        # Effectively disabling sending
        context.user_data['sending'] = False

        # Check if the pressed button has the callback_data 'button_A'
        if button_data == 'balance':
            balanc_bcr = self._db.get_balance(phone)[0]
            balance_check_text = get_translation(user_lang, 'balance_key', balanc_bcr=balanc_bcr)
            await query.message.reply_text(balance_check_text)
        elif button_data == 'send':
            await query.message.reply_text(enter_phone_text)
            context.user_data['sending'] = True
            context.user_data['phone'] = None
            context.user_data['amount'] = None
        else:
            await query.message.reply_text(unknown_command_text)
        
        await query.answer()

    # Message handler for sending balance
    async def send_handler(self, update: Update, context: CallbackContext) -> None:
        def clean_phone_number(phone_number):

            if not phone_number.startswith("+"):
                return None
            
            if len(phone_number) > 15:
                return None

            match = re.findall(r'\d', phone_number)

            if match:
                cleaned_number = '+' + ''.join(match)
                return cleaned_number
            else:
                return None

        def clean_int(input_string):
            if len(input_string) > 16:
                return 0
            try:
                # Try to convert the input string to a Decimal
                number = Decimal(input_string)
                
                # Check if the number is a rational number
                if number % 1 == 0:
                    # If it's an integer, return it as is
                    return int(number)
                else:
                    # If it's a rational number, ceil it
                    return math.ceil(number)
            except:
                # If the conversion fails, it's not a number
                return 0

        if context.user_data.get("sending") == False:
            return

        user_id = context._user_id
        user_lang = self._db.get_user_language(user_id) or default_language_code
        snd_phone = self._db.get_assoc(user_id)
        recv_phone = context.user_data.get("phone")
        recv_amount = context.user_data.get("amount")
        phone = self._db.get_assoc(user_id)

        unauthorized_text = get_translation(user_lang, 'unauthorized_key')
        user_not_found_text = get_translation(user_lang, 'user_not_found_key')
        enter_amount_text = get_translation(user_lang, 'enter_amount_key')
        incorrect_number_text = get_translation(user_lang, 'incorrect_number_key')
        incorrect_amount_text = get_translation(user_lang, 'incorrect_amount_key')
        enter_comment_text = get_translation(user_lang, 'enter_comment_key')
        transfer_request_sent_text = get_translation(user_lang, 'transfer_request_sent_key', amount=recv_amount, phone=recv_phone)

        if not phone:
            await update.message.reply_text(unauthorized_text)
            return
        
        if recv_phone == None:
            # Handling phone
            phone = clean_phone_number(update.message.text)
            if phone:
                user = self._db.get_user(phone)
                
                if not user:
                    await update.message.reply_text(user_not_found_text)
                    return

                context.user_data['phone'] = phone
                await update.message.reply_text(enter_amount_text)
            else:
                await update.message.reply_text(incorrect_number_text)
        elif recv_amount == None:
            # Handling amount
            amount = clean_int(update.message.text)
            if (amount > 0):
                context.user_data['amount'] = amount
                await update.message.reply_text(enter_comment_text)
            else:
                await update.message.reply_text(incorrect_amount_text)
        else:
            # Handling comment
            comment = update.message.text
            context.user_data['phone'] = None
            context.user_data['amount'] = None
            sender_info = self._db.get_user_info_with_balance(snd_phone[0])
            receiver_info = self._db.get_user_info_with_balance(recv_phone)

            self._db.create_pending_action(
                amount=recv_amount,
                user_phone_number=snd_phone[0],
                receiver_phone_number=recv_phone,
                comment=comment,
                sender_info=sender_info,
                receiver_info=receiver_info
            )
            await update.message.reply_text(transfer_request_sent_text)

    async def language_command(self, update: Update, context: CallbackContext) -> None:
        keyboard = [
            [
                InlineKeyboardButton("🇺🇸", callback_data='en'),
                InlineKeyboardButton("🇷🇺", callback_data='ru')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Please choose your language:', reply_markup=reply_markup)    

    async def stats_command(self, update: Update, context: CallbackContext):
        user_id = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
        if user_id not in AUTHORIZED_ADMINS:
            text = "У вас нет доступа к этой команде."
            if update.callback_query:
                await update.callback_query.answer(text, show_alert=True)
            else:
                await update.message.reply_text(text)
            return

        statistics = self._db.get_users_statistics()
        if statistics:
            message = (
                    f"`Всего пользователей:`* {statistics['total_users']}*\n"
                    f"`С положительным балансом:`* {statistics['positive_balance_users']}*\n"
                    f"`С 0 балансом:`* {statistics['zero_balance_users']}*\n"
                    f"`С минус балансом:`* {statistics['negative_balance_users']}*\n"
                    f"`Общий баланс ноль:`* {statistics['overall_zero']}*\n"
                    f"`Пользователей без информации:`* {statistics['users_without_info']}*"
                )
            if update.callback_query:
                await update.callback_query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            text = "Не удалось получить статистику."
            if update.callback_query:
                await update.callback_query.answer(text, show_alert=True)
            else:
                await update.message.reply_text(text)

    async def language_callback_handler(self, update: Update, context: CallbackContext) -> None:
        query = update.callback_query
        language_code = query.data  # 'en' или 'ru'
        user_id = query.from_user.id
        
        # Сохранение выбранного языка в базе данных
        self._db.set_user_language(user_id, language_code)
        
        # Отправка подтверждения пользователю
        language_set_text = get_translation(language_code, 'language_set_key', language_code=language_code) 
        await query.edit_message_text(text=language_set_text)
        await query.answer()

    def run(self):

        # Add other handlers after the ConversationHandlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("statistics", self.stats_command))
        self.application.add_handler(CommandHandler("balance_bcr", self.actions_command))
        self.application.add_handler(CommandHandler("language", self.language_command))
        self.application.add_handler(MessageHandler(filters.CONTACT, self.phone_auth))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.send_handler))
        self.application.add_handler(CallbackQueryHandler(self.stats_command, pattern='^get_stats$'))
        self.application.add_handler(CallbackQueryHandler(self.language_callback_handler, pattern='^(en|ru)$'))
        self.application.add_handler(CallbackQueryHandler(self.keyboard_handler))

        # Start the bot
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)