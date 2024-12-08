from flask import Flask, request  # Importamos Flask y la clase 'request'

# Crear la aplicación Flask
app = Flask(__name__)  # Se crea una instancia de la aplicación Flask

# Ruta para recibir señales de TradingView
@app.route('/webhook', methods=['POST'])  # Ruta que recibe datos por HTTP POST
def webhook():
    try:
        data = request.get_json()  # Obtenemos datos JSON del cuerpo de la solicitud
        print(f"Señal recibida: {data}")

        # Validar la señal
        if "action" not in data or data["action"] not in ["buy", "sell"]:
            return "Señal inválida", 400

        # Ejecutar lógica según los datos recibidos (omito detalles aquí para resumir)
        return {"status": "success"}, 200
    except Exception as e:
        print(f"Error en la recepción de la señal: {e}")
        return {"status": "error", "message": str(e)}, 500

# Este bloque inicia la aplicación si se ejecuta el script
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))  # Puerto que usará Flask (puede configurarse por variable de entorno)
    app.run(host="0.0.0.0", port=port)  # Inicia el servidor Flask
