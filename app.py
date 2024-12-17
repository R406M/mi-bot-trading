from flask import Flask, request, jsonify
from kucoin.client import Trade, Market
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

# Configuración fija
SYMBOL = "DOGE-USDT"  # Par de trading
TAKE_PROFIT = 0.2  # Ganancia fija (USDT)
STOP_LOSS = 10.0   # Pérdida fija (USDT)

# Estado del bot
operation_in_progress = False  # Controla si ya hay una operación activa


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

    # Extraer acción y monto de la señal
    action = data.get('action')
    amount = float(data.get('amount', 0))  # Monto enviado desde la señal

    if action and amount > 0:  # Asegurarse de que los datos sean válidos
        try:
            # Iniciar operación
            operation_in_progress = True

            # Obtener el precio actual del mercado
            ticker = market_client.get_ticker(SYMBOL)  # CORRECCIÓN: Usar cliente Market
            current_price = float(ticker['price'])

            # Calcular Take Profit (TP) y Stop Loss (SL)
            tp_price = current_price + TAKE_PROFIT if action == "buy" else current_price - TAKE_PROFIT
            sl_price = current_price - STOP_LOSS if action == "buy" else current_price + STOP_LOSS

            # Ejecutar la orden de compra o venta
            try:
                response = trade_client.create_market_order(
                    symbol=SYMBOL,
                    side=action,
                    funds=amount  # Compramos con los USDT indicados en "amount"
                )
                print(f"Orden {action} realizada: {response}")
            except Exception as e:
                print(f"Error al ejecutar la orden {action}: {e}")
                return jsonify({"error": f"Error al ejecutar la orden {action}: {str(e)}"}), 500

            # Simulación de TP/SL (debe integrarse con un bot de monitoreo de precios si es real)
            print(f"TP configurado en {tp_price} USDT, SL configurado en {sl_price} USDT")

            # Finalizar operación
            operation_in_progress = False
            return jsonify({
                "status": "success",
                "message": f"Orden {action} ejecutada",
                "take_profit": tp_price,
                "stop_loss": sl_price
            }), 200

        except Exception as e:
            # Manejar errores en la operación
            operation_in_progress = False
            print(f"Error al ejecutar la orden {action}: {e}")
            return jsonify({"error": f"Error al ejecutar la orden {action}"}), 500
    else:
        return jsonify({"error": "Datos incompletos"}), 400




if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)




