from flask import Flask, request, jsonify
from kucoin.client import Trade, Market, User
import os
import threading
import time
import logging

# Configuración del bot
app = Flask(__name__)
SECRET_TOKEN = os.getenv("WEBHOOK_SECRET", "ROSE")

# Credenciales de la API de KuCoin
API_KEY = os.getenv("KUCOIN_API_KEY")
API_SECRET = os.getenv("KUCOIN_SECRET_KEY")
API_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")

# Configuración fija
SYMBOL = "DOGE-USDT"
TAKE_PROFIT_PERCENT = 0.2
STOP_LOSS_PERCENT = 0.5

# Clientes de KuCoin
try:
    trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)
    market_client = Market()
    user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)
except Exception as e:
    app.logger.error(f"Error inicializando clientes KuCoin: {e}")
    raise SystemExit("Error crítico al conectar con KuCoin")

# Estado del bot
class BotState:
    def __init__(self):
        self.operation_in_progress = False
        self.current_order = {}

state = BotState()

# Configuración de logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    logger.info(f"Datos recibidos: {data}")

    if not data or data.get('token') != SECRET_TOKEN:
        logger.error("Token inválido recibido.")
        return jsonify({"error": "Token inválido"}), 403

    action = data.get('action')

    if action not in ['buy', 'sell']:
        logger.error("Acción inválida recibida.")
        return jsonify({"error": "Acción inválida"}), 400

    if state.operation_in_progress and state.current_order.get('side') != action:
        logger.warning("Operación en curso pero señal opuesta recibida, cerrando operación actual...")
        close_current_operation()

    if state.operation_in_progress:
        logger.warning("Operación en curso, señal rechazada.")
        return jsonify({"status": "busy", "message": "Esperando a que finalice la operación actual"}), 200

    try:
        state.operation_in_progress = True
        ticker = safe_get_ticker(SYMBOL)
        if not ticker:
            raise Exception("No se pudo obtener el ticker")

        current_price = float(ticker['price'])
        logger.info(f"Precio actual del mercado para {SYMBOL}: {current_price}")

        if action == "buy":
            handle_buy(current_price)
        elif action == "sell":
            handle_sell(current_price)

        threading.Thread(target=monitor_price, daemon=True).start()

        return jsonify({
            "status": "success",
            "message": f"Orden {action} ejecutada",
            "tp_price": state.current_order['tp_price'],
            "sl_price": state.current_order['sl_price']
        }), 200

    except Exception as e:
        logger.error(f"Error procesando la señal: {e}")
        state.operation_in_progress = False
        return jsonify({"error": str(e)}), 500

def handle_buy(current_price):
    usdt_balance = safe_get_balance("USDT") * 0.85
    if usdt_balance > 0:
        adjusted_amount = usdt_balance / current_price
        adjusted_amount = adjust_to_increment(adjusted_amount, 0.001)

        response = safe_create_order(SYMBOL, "buy", funds=round(usdt_balance, 2))
        logger.info(f"Compra ejecutada: {response}")
        state.current_order.update({
            "side": "buy",
            "tp_price": current_price * (1 + TAKE_PROFIT_PERCENT),
            "sl_price": current_price * (1 - STOP_LOSS_PERCENT)
        })
    else:
        raise Exception("Saldo insuficiente de USDT")

def handle_sell(current_price):
    doge_balance = safe_get_balance("DOGE") * 0.85
    if doge_balance > 0:
        adjusted_amount = adjust_to_increment(doge_balance, 0.001)

        response = safe_create_order(SYMBOL, "sell", size=adjusted_amount)
        logger.info(f"Venta ejecutada: {response}")
        state.current_order.update({
            "side": "sell",
            "tp_price": current_price * (1 - TAKE_PROFIT_PERCENT),
            "sl_price": current_price * (1 + STOP_LOSS_PERCENT)
        })
    else:
        raise Exception("Saldo insuficiente de DOGE")

def close_current_operation():
    if state.current_order['side'] == "buy":
        sell_all()
        logger.info("Operación de compra cerrada manualmente.")
    elif state.current_order['side'] == "sell":
        sell_all()
        logger.info("Operación de venta cerrada manualmente.")
    state.operation_in_progress = False
    state.current_order.clear()

def monitor_price():
    while state.operation_in_progress:
        try:
            ticker = safe_get_ticker(SYMBOL)
            if not ticker:
                break
            current_price = float(ticker['price'])
            logger.info(f"Precio actual monitoreado: {current_price}")

            if state.current_order['side'] == "buy":
                if current_price >= state.current_order['tp_price'] or current_price <= state.current_order['sl_price']:
                    sell_all()
                    break
            elif state.current_order['side'] == "sell":
                if current_price <= state.current_order['tp_price'] or current_price >= state.current_order['sl_price']:
                    break

            time.sleep(1)

        except Exception as e:
            logger.error(f"Error monitoreando el precio: {e}")
            break

    state.operation_in_progress = False
    state.current_order.clear()

def sell_all():
    doge_balance = safe_get_balance("DOGE") * 0.98
    if doge_balance > 0:
        response = safe_create_order(SYMBOL, "sell", size=round(doge_balance, 2))
        logger.info(f"Orden de venta ejecutada: {response}")

def safe_get_balance(asset):
    """Obtener el balance de un activo (USDT o DOGE) de forma segura."""
    retries = 3
    for i in range(retries):
        try:
            accounts = user_client.get_account_list()  # Obtener todas las cuentas
            for account in accounts:
                if account['currency'] == asset and account['type'] == 'trade':
                    return float(account['available'])  # Saldo disponible
            return 0  # Si no se encuentra el saldo del activo
        except Exception as e:
            app.logger.error(f"Error obteniendo saldo para {asset}: ({i+1}/{retries}) {e}")
            time.sleep(5)
    return 0

def safe_get_ticker(symbol):
    retries = 3
    for i in range(retries):
        try:
            return market_client.get_ticker(symbol)
        except Exception as e:
            logger.error(f"Error obteniendo ticker para {symbol}: ({i+1}/{retries}) {e}")
            time.sleep(5)
    return None

def safe_create_order(symbol, side, **kwargs):
    retries = 3
    for i in range(retries):
        try:
            if side == "buy":
                return trade_client.create_market_order(symbol, side, funds=kwargs['funds'])
            else:
                return trade_client.create_market_order(symbol, side, size=kwargs['size'])
        except Exception as e:
            logger.error(f"Error creando orden {side} para {symbol}: ({i+1}/{retries}) {e}")
            time.sleep(5)
    return None

def adjust_to_increment(amount, min_increment):
    return round(amount / min_increment) * min_increment

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=False)
