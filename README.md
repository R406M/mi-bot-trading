# Mi Bot de Trading

Este es un bot de trading que conecta TradingView con KuCoin usando Render. El bot recibe señales de TradingView mediante webhooks y ejecuta órdenes de compra/venta en KuCoin.

## Características
- Conexión en tiempo real entre TradingView y KuCoin.
- Ejecución de órdenes de mercado con take-profit y stop-loss.
- Uso del 90% del saldo disponible, dejando el 10% para comisiones.
- Alojado en Render para operar 24/7.

## Requisitos
- Python 3.8 o superior.
- Cuenta en KuCoin con API habilitada.
- Cuenta en TradingView con capacidad para enviar webhooks.
- Cuenta en Render para alojar el bot.

## Instalación
1. Clona este repositorio:
   ```bash
   git clone https://github.com/R406M/mi-bot-trading.git
   cd mi-bot-trading
