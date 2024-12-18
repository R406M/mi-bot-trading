from flask import Flask, request, jsonify
from kucoin.client import Trade, Market, Client  # Cambié Account a Client
import os
import time

# Configuración del bot
app = Flask(__name__)
SECRET_TOKEN = os.getenv("WEBHOOK_SECRET", "ROSE")  # Configurado en las variables de entorno

# Credenciales de la API de KuCoin (cargar desde variables de entorno)
API_KEY = os.getenv("KUCOIN_API_KEY")
API_SECRET = os.getenv("KUCOIN_SECRET_KEY")
API_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")

# Conexión a los clientes de KuCoin
trade_client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHSE)
market_client = Market()  # Cliente para obtener datos del mercado
client = Client(API_KEY, API_SECRET)  # Usamos Client para obtener el saldo

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

    if action:
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
            if action == "buy":
                # Obtener el saldo de USDT disponible
                accounts = client.get_accounts()  # Usamos Client para obtener las cuentas
                usdt_balance = next((account['balance'] for account in accounts if account['currency'] == 'USDT'), 0)

                if usdt_balance > 0:
                    # Realizar la compra con todo el saldo disponible en USDT
                    response = trade_client.create_market_order(
                        symbol=SYMBOL,
                        side=action,
                        funds=usdt_balance  # Usamos todo el saldo en USDT
                    )
                    print(f"Orden {action} realizada: {response}")
                    
                    # Monitorear el precio para TP y SL
                    while operation_in_progress:
                        ticker = market_client.get_ticker(SYMBOL)
                        current_price = float(ticker['price'])
                        print(f"Precio actual: {current_price}")

                        if action == "buy":
                            if current_price >= tp_price:
                                print(f"Take Profit alcanzado: {current_price}")
                                # Vender todo el DOGE
                                doge_balance = next((account['balance'] for account in accounts if account['currency'] == 'DOGE'), 0)
                                trade_client.create_market_order(symbol=SYMBOL, side="sell", funds=doge_balance)
                                print(f"Orden de venta ejecutada con TP en {tp_price}")
                                break
                            elif current_price <= sl_price:
                                print(f"Stop Loss alcanzado: {current_price}")
                                # Vender todo el DOGE
                                doge_balance = next((account['balance'] for account in accounts if account['currency'] == 'DOGE'), 0)
                                trade_client.create_market_order(symbol=SYMBOL, side="sell", funds=doge_balance)
                                print(f"Orden de venta ejecutada con SL en {sl_price}")
                                break

                        time.sleep(5)  # Esperar 5 segundos antes de consultar nuevamente

            elif action == "sell":
                # Obtener el saldo de DOGE disponible
                accounts = client.get_accounts()  # Usamos Client para obtener las cuentas
                doge_balance = next((account['balance'] for account in accounts if account['currency'] == 'DOGE'), 0)

                if doge_balance > 0:
                    # Realizar la venta de todo el saldo de DOGE
                    response = trade_client.create_market_order(
                        symbol=SYMBOL,
                        side=action,
                        funds=doge_balance  # Usamos todo el saldo de DOGE
                    )
                    print(f"Orden {action} realizada: {response}")
                else:
                    return jsonify({"error": "No hay DOGE para vender"}), 400

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
            return jsonify({"error": f"Error al ejecutar la orden {action}: {str(e)}"}), 500
    else:
        return jsonify({"error": "Datos incompletos"}), 400

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
