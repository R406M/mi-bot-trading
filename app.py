from flask import Flask, request, jsonify
from kucoin.client import Trade

# Configuración del bot
app = Flask(__name__)
SECRET_TOKEN = "rose"  # Cambia esto por el token configurado en TradingView

# Credenciales de la API de KuCoin
API_KEY = "tu_api_key"
API_SECRET = "tu_api_secret"
API_PASSPHRASE = "tu_passphrase"

# Conexión al cliente de KuCoin
client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE)

@app.route('/webhook', methods=['POST'])
def webhook():
    # Recibir la señal desde TradingView
    data = request.get_json()
    
    # Validar si los datos y el token son correctos
    if not data or data.get('token') != SECRET_TOKEN:
        return jsonify({"error": "Token inválido"}), 403
    
    # Extraer acción y monto de la señal
    action = data.get('action')
    amount = data.get('amount')

    if action and amount:  # Asegurarse de que los datos sean válidos
        if action == "buy":
            try:
                # Ejecutar una orden de compra
                response = client.create_market_order(
                    symbol='DOGE-USDT',  # Cambia al par de criptomonedas que desees
                    side='buy',
                    size=amount  # Tamaño de la compra
                )
                print(f"Orden de compra realizada: {response}")
                return jsonify({"status": "success", "message": "Orden de compra ejecutada"}), 200
            except Exception as e:
                print(f"Error al realizar la compra: {e}")
                return jsonify({"error": "Error al realizar la compra"}), 500
        elif action == "sell":
            try:
                # Ejecutar una orden de venta
                response = client.create_market_order(
                    symbol='DOGE-USDT',  # Cambia al par de criptomonedas que desees
                    side='sell',
                    size=amount  # Tamaño de la venta
                )
                print(f"Orden de venta realizada: {response}")
                return jsonify({"status": "success", "message": "Orden de venta ejecutada"}), 200
            except Exception as e:
                print(f"Error al realizar la venta: {e}")
                return jsonify({"error": "Error al realizar la venta"}), 500
        else:
            return jsonify({"error": "Acción no válida"}), 400
    else:
        return jsonify({"error": "Datos incompletos"}), 400

if __name__ == '__main__':
    app.run(debug=True)


