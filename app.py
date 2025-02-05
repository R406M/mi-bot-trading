import os
import time
import threading
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass
import ccxt
from flask import Flask, request, jsonify
from loguru import logger
from dotenv import load_dotenv

# Configuración de logging
logger.add("trading_bot.log", rotation="500 MB", retention="10 days")

# Cargar variables de entorno
load_dotenv()

@dataclass
class Position:
    entry_price: float
    size: float
    side: str
    tp_price: float
    sl_price: float
    timestamp: float

class TradingBot:
    def __init__(self):
        self.api_key = os.getenv('KUCOIN_API_KEY')
        self.api_secret = os.getenv('KUCOIN_API_SECRET')
        self.api_passphrase = os.getenv('KUCOIN_PASSPHRASE')

        self.symbol = "DOGE-USDT"
        self.tp_percentage = 0.002  # 0.2%
        self.sl_percentage = 0.005  # 0.5%
        self.reserve_percentage = 0.10  # 10% reserva

        self.exchange = self._initialize_exchange()
        self.current_position: Optional[Position] = None
        self.position_monitor_thread = None
        self.should_monitor = False

        # Iniciar monitoreo de posiciones
        self.start_position_monitor()

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Inicializa la conexión con KuCoin"""
        try:
            exchange = ccxt.kucoin({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'password': self.api_passphrase,
                'enableRateLimit': True
            })
            return exchange
        except Exception as e:
            logger.error(f"Error inicializando exchange: {e}")
            raise

    def get_current_price(self) -> float:
        """Obtiene el precio actual del mercado"""
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            return float(ticker['last'])
        except Exception as e:
            logger.error(f"Error obteniendo precio: {e}")
            raise

    def get_balance(self) -> Dict:
        """Obtiene el balance de la cuenta"""
        try:
            balance = self.exchange.fetch_balance()
            return {
                'USDT': float(balance['USDT']['free']),
                'DOGE': float(balance['DOGE']['free'])
            }
        except Exception as e:
            logger.error(f"Error obteniendo balance: {e}")
            raise

    def execute_market_order(self, side: str, amount: float) -> Dict:
        """Ejecuta una orden de mercado"""
        try:
            order = self.exchange.create_market_order(
                symbol=self.symbol,
                side=side,
                amount=amount if side == 'sell' else None,
                cost=amount if side == 'buy' else None
            )
            logger.info(f"Orden ejecutada: {order}")
            return order
        except Exception as e:
            logger.error(f"Error ejecutando orden: {e}")
            raise

    def start_position_monitor(self):
        """Inicia el monitor de posiciones en un thread separado"""
        if not self.position_monitor_thread:
            self.should_monitor = True
            self.position_monitor_thread = threading.Thread(target=self._monitor_positions)
            self.position_monitor_thread.daemon = True
            self.position_monitor_thread.start()

    def _monitor_positions(self):
        """Monitorea las posiciones abiertas para TP/SL"""
        while self.should_monitor:
            try:
                if self.current_position:
                    current_price = self.get_current_price()

                    # Verificar TP
                    if (self.current_position.side == 'buy' and
                        current_price >= self.current_position.tp_price):
                        self.close_position("TP alcanzado")

                    # Verificar SL
                    elif (self.current_position.side == 'buy' and
                          current_price <= self.current_position.sl_price):
                        self.close_position("SL alcanzado")

                    # Para posiciones en venta
                    elif (self.current_position.side == 'sell' and
                          current_price <= self.current_position.tp_price):
                        self.close_position("TP alcanzado (venta)")

                    elif (self.current_position.side == 'sell' and
                          current_price >= self.current_position.sl_price):
                        self.close_position("SL alcanzado (venta)")

            except Exception as e:
                logger.error(f"Error en monitoreo: {e}")

            time.sleep(1)  # Esperar 1 segundo entre verificaciones

    def close_position(self, reason: str):
        """Cierra la posición actual"""
        try:
            if self.current_position:
                side = 'sell' if self.current_position.side == 'buy' else 'buy'
                self.execute_market_order(side, self.current_position.size)
                logger.info(f"Posición cerrada: {reason}")
                self.current_position = None
        except Exception as e:
            logger.error(f"Error cerrando posición: {e}")

    def process_signal(self, signal_side: str):
        """Procesa una nueva señal de trading"""
        try:
            # Si hay una posición abierta, cerrarla
            if self.current_position:
                self.close_position("Nueva señal recibida")

            current_price = self.get_current_price()
            balance = self.get_balance()

            # Calcular cantidad a operar (90% del balance)
            if signal_side == 'buy':
                available_usdt = balance['USDT'] * (1 - self.reserve_percentage)
                size = available_usdt / current_price
            else:  # sell
                available_doge = balance['DOGE'] * (1 - self.reserve_percentage)
                size = available_doge

            # Ejecutar nueva orden
            order = self.execute_market_order(signal_side, size)

            # Calcular TP y SL
            if signal_side == 'buy':
                tp_price = current_price * (1 + self.tp_percentage)
                sl_price = current_price * (1 - self.sl_percentage)
            else:
                tp_price = current_price * (1 - self.tp_percentage)
                sl_price = current_price * (1 + self.sl_percentage)

            # Registrar nueva posición
            self.current_position = Position(
                entry_price=current_price,
                size=size,
                side=signal_side,
                tp_price=tp_price,
                sl_price=sl_price,
                timestamp=time.time()
            )

            return {
                "status": "success",
                "message": f"Orden {signal_side} ejecutada",
                "entry_price": current_price,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "size": size
            }

        except Exception as e:
            logger.error(f"Error procesando señal: {e}")
            raise

# Inicializar Flask y el bot
app = Flask(__name__)
trading_bot = TradingBot()

@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint para recibir señales de TradingView"""
    try:
        data = request.json

        # Validar datos
        if not data or 'side' not in data:
            return jsonify({"error": "Datos inválidos"}), 400

        side = data['side'].lower()
        if side not in ['buy', 'sell']:
            return jsonify({"error": "Señal inválida"}), 400

        # Procesar señal
        result = trading_bot.process_signal(side)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Render asigna el puerto en la variable PORT
    app.run(host='0.0.0.0', port=port)
