import os
import logging
from flask import Flask, request, jsonify
import ccxt

# Configuración básica de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='bot.log'  # Guarda los logs en un archivo
)

app = Flask(__name__)

# Configuración de KuCoin
api_key = os.getenv('KUCOIN_API_KEY')        # Clave de API desde variables de entorno
api_secret = os.getenv('KUCOIN_API_SECRET')  # Secreto de API desde variables de entorno
api_passphrase = os.getenv('KUCOIN_PASSPHRASE')  # Passphrase desde variables de entorno

# Inicializar el exchange de KuCoin
exchange = ccxt.kucoin({
    'apiKey': api_key,
    'secret': api_secret,
    'password': api_passphrase,
    'enableRateLimit': True,  # Habilita el límite de tasa para evitar baneos
})

# Par de trading
SYMBOL = 'DOGE/USDT'

# Take-profit y stop-loss en USDT
TAKE_PROFIT = 0.2  # 0.2 USDT
STOP_LOSS = 0.5    # 0.5 USDT

# Porcentaje del saldo a usar (90%)
BALANCE_PERCENTAGE = 0.9

# Ruta para recibir señales de TradingView
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Obtener los datos de la solicitud
        data = request.json

        # Validar que la señal sea completa
        if not all(key in data for key in ['side']):
            logging.error("Señal incompleta recibida: %s", data)
            return jsonify({"status": "error", "message": "Señal incompleta"}), 400

        # Extraer los datos de la señal
        side = data['side']  # 'buy' o 'sell'

        # Validar que el lado de la operación sea correcto
        if side not in ['buy', 'sell']:
            logging.error("Lado de operación inválido: %s", side)
            return jsonify({"status": "error", "message": "Lado de operación inválido"}), 400

        # Obtener el saldo disponible en USDT
        balance = exchange.fetch_balance()
        usdt_balance = balance['total']['USDT']  # Saldo total en USDT
        available_balance = usdt_balance * BALANCE_PERCAGE  # Usar el 90% del saldo

        # Obtener el precio actual de DOGE/USDT
        ticker = exchange.fetch_ticker(SYMBOL)
        current_price = ticker['last']

        # Calcular la cantidad de DOGE a comprar/vender
        amount = available_balance / current_price  # Cantidad en DOGE

        # Calcular precios de TP y SL
        if side == 'buy':
            tp_price = current_price + (TAKE_PROFIT / amount)  # Precio de take-profit
            sl_price = current_price - (STOP_LOSS / amount)    # Precio de stop-loss
        else:
            tp_price = current_price - (TAKE_PROFIT / amount)  # Precio de take-profit
            sl_price = current_price + (STOP_LOSS / amount)    # Precio de stop-loss

        # Ejecutar la orden de mercado
        try:
            market_order = exchange.create_order(SYMBOL, 'market', side, amount)
            logging.info("Orden de mercado ejecutada: %s", market_order)

            # Colocar órdenes de take-profit y stop-loss
            if side == 'buy':
                tp_order = exchange.create_order(SYMBOL, 'limit', 'sell', amount, tp_price)
                sl_order = exchange.create_order(SYMBOL, 'limit', 'sell', amount, sl_price)
            else:
                tp_order = exchange.create_order(SYMBOL, 'limit', 'buy', amount, tp_price)
                sl_order = exchange.create_order(SYMBOL, 'limit', 'buy', amount, sl_price)

            logging.info("Orden de take-profit colocada: %s", tp_order)
            logging.info("Orden de stop-loss colocada: %s", sl_order)

            return jsonify({
                "status": "success",
                "market_order": market_order,
                "tp_order": tp_order,
                "sl_order": sl_order,
                "usdt_balance": usdt_balance,
                "used_balance": available_balance
            }), 200

        except Exception as e:
            logging.error("Error al ejecutar órdenes: %s", str(e))
            return jsonify({"status": "error", "message": str(e)}), 500

    except Exception as e:
        logging.error("Error en el webhook: %s", str(e))
        return jsonify({"status": "error", "message": "Error interno del servidor"}), 500

# Iniciar el servidor
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
