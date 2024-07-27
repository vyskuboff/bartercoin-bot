import psycopg2
from threading import Lock

class DatabaseManager:
    def __init__(self, db_params={'host': 'your_host', 'database': 'your_database', 'user': 'your_user', 'password': 'your_password', 'port': 'your_port'}):
        # Connect to the database
        self.conn = psycopg2.connect(**db_params)
        self.cursor = self.conn.cursor()
        self.lock = Lock()

        # Create the users table if it does not exist
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                phone_number TEXT NOT NULL,
                balance BIGINT NOT NULL,
                info TEXT,
				mir_karta TEXT,
				mir_account TEXT,
				balance_mir_karta TEXT,
				bcr_plast_karta_nomer TEXT,
				bcr_plast_karta_srok TEXT,
				bcr_plast_karta_cvv TEXT
            )
        ''')

        # Create the telegram-phone table if it does not exist
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS assoc (
                user_id BIGINT NOT NULL PRIMARY KEY,
                phone_number TEXT NOT NULL,
                language VARCHAR(3) DEFAULT 'ru'
            )
        ''')

        # Create the pending_actions table if it does not exist
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_actions (
                id SERIAL PRIMARY KEY,
                user_phone_number TEXT NOT NULL,
                receiver_phone_number TEXT NOT NULL,
                amount BIGINT NOT NULL,
                comment TEXT NOT NULL,
                sender_info TEXT,
                receiver_info TEXT
            )
        ''')

        # Create the actions table if it does not exist
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS actions (
                id SERIAL PRIMARY KEY,
                user_phone_number TEXT NOT NULL,
                receiver_phone_number TEXT NOT NULL,
                amount BIGINT NOT NULL,
                md5 TEXT NOT NULL,
                comment TEXT
            )
        ''')

        self.conn.commit()

    def get_users_statistics(self):
        with self.lock:
            try:
                # Общее количество пользователей
                self.cursor.execute("SELECT COUNT(*) FROM users")
                total_users = self.cursor.fetchone()[0]

                # Количество пользователей с положительным балансом
                self.cursor.execute("SELECT COUNT(*) FROM users WHERE balance > 0")
                positive_balance_users = self.cursor.fetchone()[0]

                # Количество пользователей с нулевым балансом
                self.cursor.execute("SELECT COUNT(*) FROM users WHERE balance = 0")
                zero_balance_users = self.cursor.fetchone()[0]

                # Количество пользователей с отрицательным балансом
                self.cursor.execute("SELECT COUNT(*) FROM users WHERE balance < 0")
                negative_balance_users = self.cursor.fetchone()[0]

                # Общий баланс (да/нет)
                self.cursor.execute("SELECT SUM(balance) FROM users")
                total_balance = self.cursor.fetchone()[0]
                overall_zero = 'Да' if total_balance == 0 else 'Нет'

                # Количество пользователей без информации
                self.cursor.execute("SELECT COUNT(*) FROM users WHERE info IS NULL OR info = ''")
                users_without_info = self.cursor.fetchone()[0]

                # Собираем статистику в словарь
                statistics = {
                    'total_users': total_users,
                    'positive_balance_users': positive_balance_users,
                    'zero_balance_users': zero_balance_users,
                    'negative_balance_users': negative_balance_users,
                    'overall_zero': overall_zero,
                    'users_without_info': users_without_info
                }
                return statistics
            except psycopg2.Error as e:
                print(f"Error fetching users statistics: {e}")
                return None

    def add_user(self, phone_number):
        # Self-explanatory
        with self.lock:
            self.cursor.execute('INSERT INTO users (phone_number, balance) VALUES (%s, 0)', (phone_number,))
            self.conn.commit()

    def get_user(self, phone_number):
        # Self-explanatory
        with self.lock:
            self.cursor.execute('SELECT * FROM users WHERE phone_number=%s', (phone_number,))
            return self.cursor.fetchone()

    def add_assoc(self, user_id, phone_number):
        with self.lock:
            # Add association between telegram user id and a phone number
            self.cursor.execute('INSERT INTO assoc (user_id, phone_number) VALUES (%s, %s)', (user_id, phone_number))
            self.conn.commit()

    def get_assoc(self, user_id):
        with self.lock:
            # Self-explanatory
            self.cursor.execute('SELECT phone_number FROM assoc WHERE user_id=%s', (user_id,))
            return self.cursor.fetchone()

    def get_reverse_assoc(self, phone_number):
        with self.lock:
            # Self-explanatory
            self.cursor.execute('SELECT user_id FROM assoc WHERE phone_number=%s', (phone_number,))
            return self.cursor.fetchone()

    def get_balance(self, phone_number):
        with self.lock:
            self.cursor.execute('SELECT balance FROM users WHERE phone_number=%s', (phone_number,))
            return self.cursor.fetchone()

    def get_all_pending_actions(self):
        with self.lock:
            self.cursor.execute('SELECT * FROM pending_actions')
            return self.cursor.fetchall()

    def get_user_info_by_phone(self, phone_number):
        with self.lock:
            try:
                self.cursor.execute("SELECT info FROM users WHERE phone_number = %s", (phone_number,))
                user_info = self.cursor.fetchone()
                return user_info[0] if user_info else None
            except psycopg2.Error as e:
                print(f"Error fetching user info: {e}")
                return None
				
    def get_user_info_with_balance(self, phone_number):
        with self.lock:
            try:
                self.cursor.execute("SELECT info, balance FROM users WHERE phone_number = %s", (phone_number,))
                user_info = self.cursor.fetchone()
                if user_info:
                    info, balance = user_info
                    if info:
                        info = f"Баланс: {balance}\n" + info.strip()
                    else:
                        info = f"Баланс: {balance}"
                    return info
                else:
                    return None
            except psycopg2.Error as e:
                print(f"Error fetching user info with balance: {e}")
                return None

    def create_pending_action(self, user_phone_number, receiver_phone_number, amount, sender_info, receiver_info, comment):
        with self.lock:
            try:
                self.cursor.execute('''
                    INSERT INTO pending_actions (user_phone_number, receiver_phone_number, amount, sender_info, receiver_info, comment)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (user_phone_number, receiver_phone_number, amount, sender_info, receiver_info, comment))
                self.conn.commit()
                return True
            except psycopg2.Error as e:
                print(f"Error creating pending action: {e}")
                self.conn.rollback()
                return False

    def remove_pending_action(self, id):
        # Self-explanatory
        with self.lock:

            self.cursor.execute('SELECT user_phone_number, amount FROM pending_actions WHERE id=%s', (id,))
            result = self.cursor.fetchone()
            if result:
                recv_phone, amount = result
                self.cursor.execute('DELETE FROM pending_actions WHERE id=%s', (id,))
                self.conn.commit()
                return recv_phone, amount
            return None

    def apply_pending_action(self, id, md5):
        # Retrieve data from pending_actions
        with self.lock:
            self.cursor.execute('''
                SELECT user_phone_number, receiver_phone_number, amount, comment
                FROM pending_actions
                WHERE id = %s
            ''', (id,))
            pending_action_data = self.cursor.fetchone()

            if pending_action_data:
                user_phone_number, receiver_phone_number, amount, comment = pending_action_data

                # Update sender's balance (decrease by amount)
                self.cursor.execute('UPDATE users SET balance = balance - %s WHERE phone_number=%s', (amount, user_phone_number))

                # Update receiver's balance (increase by amount)
                self.cursor.execute('UPDATE users SET balance = balance + %s WHERE phone_number=%s', (amount, receiver_phone_number))

                # Remove from pending_actions
                self.cursor.execute('DELETE FROM pending_actions WHERE id=%s', (id,))
                self.conn.commit()

                # Add to actions
                self.cursor.execute('''
                    INSERT INTO actions (user_phone_number, receiver_phone_number, amount, md5, comment)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (user_phone_number, receiver_phone_number, amount, md5, comment))
                self.conn.commit()
                return (user_phone_number, receiver_phone_number, amount, comment)
            return None

    def get_last_md5(self):
        # Self-explanatory
        with self.lock:
            self.cursor.execute('SELECT md5 FROM actions ORDER BY id DESC LIMIT 1')
            return self.cursor.fetchone()

    def set_user_language(self, user_id, language_code):
        with self.lock:
            # SQL-запрос для обновления языка пользователя
            query = "UPDATE assoc SET language = %s WHERE user_id = %s"
            params = (language_code, user_id)
            self.cursor.execute(query, params)
            self.conn.commit()

    def get_user_language(self, user_id):
        with self.lock:
            # SQL-запрос для получения языка пользователя
            query = "SELECT language FROM assoc WHERE user_id = %s"
            params = (user_id,)
            self.cursor.execute(query, params)
            result = self.cursor.fetchone()
            if result:
                return result[0]
            else:
                return None