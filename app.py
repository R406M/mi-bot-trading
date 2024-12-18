from flask import Flask, request, jsonify
from kucoin.client import Trade, Market, User
import os

# Configuración del bot
app = Flask(__name__)
SECRET_TOKEN = os.getenv("WEBHOOK_SECRET", "ROSE")  # Configurado en las variables de entorno

# Credenciales de la API de KuCoin (cargar desde variables de entorno)
API_KEY = os.getenv("KUCOIN_API_KEY")
API_SECRET = os.getenv("KUCOIN_SECRET_KEY")
API_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")

# Conexión a los clientes de KuCoin
trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)
market_client = Market()  # Cliente para obtener datos del mercado
user_client = User(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)  # Cliente para consultar balances

# Configuración fija
SYMBOL = "DOGE-USDT"  # Par de trading
TAKE_PROFIT = 0.2  # Ganancia fija (USDT)
STOP_LOSS = 10.0   # Pérdida fija (USDT)

# Estado del bot
operation_in_progress = False  # Controla si ya hay una operación activa


def get_market_rules(symbol):
    """
    Obtiene las reglas de mercado para un par de trading específico.
    """
    try:
        market_info = market_client.get_symbol_list()
        for item in market_info:
            if item['symbol'] == symbol:
                return {
                    "min_funds": float(item['minFunds']),  # Cantidad mínima de compra en USDT
                    "price_increment": float(item['priceIncrement']),  # Incremento permitido en precio
                    "quantity_increment": float(item['baseIncrement'])  # Incremento permitido en cantidad (DOGE)
                }
    except Exception as e:
        print(f"Error al obtener reglas de mercado: {e}")
    return None


@app.route('/webhook', methods=['POST'])
def webhook():
    global operation_in_progress

    # Recibir la señal desde TradingView
    data = request.get_json()

    # Validar si los datos y el token son correctos
    if not data or data.get('token') != SECRET_TOKEN:
        return jsonify({"error": "Token inválido"}), 403

    # Si hay una operación en curso, rechazar nuevas señales
    if operation_in_progress:
        return jsonify({"status": "busy", "message": "Esperando a que finalice la operación actual"}), 200

    # Extraer acción de la señal
    action = data.get('action')

    if action in ["buy", "sell"]:
        try:
            # Iniciar operación
            operation_in_progress = True

            # Obtener el precio actual del mercado
            ticker = market_client.get_ticker(SYMBOL)
            current_price = float(ticker['price'])

            # Obtener reglas del mercado
            rules = get_market_rules(SYMBOL)
            if not rules:
                return jsonify({"error": "No se pudieron obtener las reglas de mercado"}), 500

            min_funds = rules["min_funds"]
            price_increment = rules["price_increment"]
            quantity_increment = rules["quantity_increment"]

            # Comprar con todo el saldo disponible en USDT
            if action == "buy":
                # Obtener todas las cuentas y filtrar la cuenta de USDT en Trading
                accounts = user_client.get_account_list()
                usdt_account = next((acc for acc in accounts if acc['currency'] == "USDT" and acc['type'] == "trade"), None)

                if not usdt_account or float(usdt_account['available']) < min_funds:
                    return jsonify({"error": f"Saldo insuficiente en USDT para realizar la compra. Mínimo requerido: {min_funds}"}), 400

                available_usdt = float(usdt_account['available'])
                # Redondear al incremento permitido por el mercado
                adjusted_usdt = available_usdt - (available_usdt % price_increment)

                response = trade_client.create_market_order(
                    symbol=SYMBOL,
                    side="buy",
                    funds=adjusted_usdt
                )

            # Vender todos los DOGE disponibles
            elif action == "sell":
                # Obtener todas las cuentas y filtrar la cuenta de DOGE en Trading
                accounts = user_client.get_account_list()
                doge_account = next((acc for acc in accounts if acc['currency'] == "DOGE" and acc['type'] == "trade"), None)

                if not doge_account or float(doge_account['available']) == 0:
                    return jsonify({"error": "No hay DOGE disponible para vender"}), 400

                available_doge = float(doge_account['available'])
                # Redondear al incremento permitido por el mercado
                adjusted_doge = available_doge - (available_doge % quantity_increment)

                response = trade_client.create_market_order(
                    symbol=SYMBOL,
                    side="sell",
                    size=adjusted_doge
                )

            print(f"Orden {action} realizada: {response}")

            # Finalizar operación
            operation_in_progress = False
            return jsonify({
                "status": "success",
                "message": f"Orden {action} ejecutada"
            }), 200

        except Exception as e:
            # Manejar errores en la operación
            operation_in_progress = False
            print(f"Error al ejecutar la orden {action}: {e}")
            return jsonify({"error": f"Error al ejecutar la orden {action}: {str(e)}"}), 500

    return jsonify({"error": "Acción inválida o datos incompletos"}), 400


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
