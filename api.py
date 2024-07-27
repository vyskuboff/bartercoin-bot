from flask import Flask, jsonify, request
from database import DatabaseManager
import hashlib
import requests
from translations import get_translation

default_language_code = 'ru'

class API:
    def __init__(self, token: str, db: DatabaseManager):
        self.app = Flask("telegram_flashback_api")
        self.db = db
        self.token = token

        # Manually set routes up
        self.app.route('/pending', methods=['GET'])(self.pending)
        self.app.route('/approve/<int:id>', methods=['POST'])(self.approve)
        self.app.route('/remove/<int:id>', methods=['POST'])(self.remove)
        self.app.route('/lastkey', methods=['GET'])(self.lastkey)

    def send_message(self, chat_id, text):
        base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        params = {
            'chat_id': chat_id,
            'text': text,
        }

        response = requests.post(base_url, params=params)
        result = response.json()
        if not result['ok']:
            print(f"Failed to send message. Telegram API response: {result}")

    def lastkey(self):
        md5 = self.db.get_last_md5()
        if md5:
            return md5[0]
        else:
            return "NO", 200

    async def auth(self, received_md5):
        latest_md5 = self.db.get_last_md5()

        if not received_md5:
            return None

        if not latest_md5:
            return received_md5

        calculated_md5 = hashlib.md5(received_md5.encode()).hexdigest()

        if calculated_md5 == latest_md5[0]:
            return received_md5
        else:
            return None

    # Return pending actions
    async def pending(self):
        md5 = await self.auth(request.args.get('md5'))
        if not md5:
            return jsonify({'error': 'Failed to authenticate'}), 401

        pending_actions = self.db.get_all_pending_actions()
        result = []
        for action in pending_actions:
            balance = self.db.get_balance(action[1])
            ltz = balance[0] < action[3]
            result.append({
                'id': action[0],
                'sender_phone': action[1],
                'receiver_phone': action[2],
                'amount': action[3],
                'comment': action[4],
                'sender_info': action[5],
                'receiver_info': action[6],
                'less_than_zero': ltz,
            })
        return jsonify(result)

    # Move pending action to a db with correct md5
    async def approve(self, id):
        md5 = await self.auth(request.json.get('md5'))
        if not md5:
            return jsonify({'error': 'Failed to authenticate'}), 401

        dbres = self.db.apply_pending_action(id, md5)

        if not (dbres == None):
            # Send message
            snd_phone, recv_phone, amount, comment = dbres
            snd_id = self.db.get_reverse_assoc(snd_phone)[0]
            recv_id = self.db.get_reverse_assoc(recv_phone)[0]
            snd_lang = self.db.get_user_language(snd_id) or default_language_code
            recv_lang = self.db.get_user_language(recv_id) or default_language_code
            approve_message_snd = get_translation(snd_lang, 'approve_message_snd',amount=amount, recv_phone=recv_phone, comment=comment)
            approve_message_recv = get_translation(recv_lang, 'approve_message_recv', amount=amount, snd_phone=snd_phone, comment=comment)

            self.send_message(snd_id, approve_message_snd)
            self.send_message(recv_id, approve_message_recv)
            return jsonify({'message': 'Action moved to actions successfully'})
        else:
            return jsonify({'error': 'Action ID not found'}), 400

    # Remove a pending action
    async def remove(self, id):
        md5 = await self.auth(request.json.get('md5'))
        if not md5:
            return jsonify({'error': 'Failed to authenticate'}), 401
        result = self.db.remove_pending_action(id)
        if result:
            # Send message
            recv_phone, amount = result
            snd_id = self.db.get_reverse_assoc(recv_phone)[0]
            snd_lang = self.db.get_user_language(snd_id) or default_language_code
            remove_message_snd = get_translation(snd_lang, 'remove_message_snd', amount=amount, recv_phone=recv_phone)

            self.send_message(snd_id, remove_message_snd)
            return jsonify({'message': 'Action removed successfully'})
        else:
            return jsonify({'error': 'Action ID not found'}), 400

    def run(self):
        from waitress import serve
        serve(self.app, host="0.0.0.0", port=5000)
