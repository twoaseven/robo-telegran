import os
import logging
import asyncio
import requests
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application
from google import genai

# --- CONFIGURAÇÕES DE AMBIENTE ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CANAL_DESTINO = os.getenv("CANAL_DESTINO", "@RadarDo_Desconto")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL") # URL gerada pelo Render

client_ai = genai.Client(api_key=GEMINI_API_KEY)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

app_flask = Flask(__name__)
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
temporario_copys = {}

@app_flask.route('/')
def home():
    return "🤖 Robô do Radar do Desconto operando 100% grátis!"

@app_flask.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    """Recebe as interações do Telegram em tempo real"""
    json_update = request.get_json(force=True)
    update = Update.de_json(json_update, telegram_app.bot)
    asyncio.run(processar_atualizacao(update))
    return "OK", 200

async def processar_atualizacao(update: Update):
    # 1. Clique nos botões de aprovação
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat_id
        acao = query.data

        if acao == "aprovar":
            copy_pronta = temporario_copys.get(chat_id)
            if not copy_pronta:
                await query.edit_message_text("⚠️ Nenhuma copy pendente encontrada.")
                return
            try:
                await telegram_app.bot.send_message(
                    chat_id=CANAL_DESTINO,
                    text=copy_pronta,
                    parse_mode="Markdown",
                    disable_web_page_preview=False
                )
                await query.edit_message_text("🚀 **Postado com sucesso no canal do Telegram!**\n\n*(Já pode copiar e jogar no WhatsApp)*")
            except Exception as e:
                await query.edit_message_text(f"❌ Erro ao postar no canal: {str(e)}")

        elif acao == "cancelar":
            await query.edit_message_text("🗑️ Postagem descartada.")

        if chat_id in temporario_copys:
            del temporario_copys[chat_id]
        return

    # 2. Envio de link no chat privado
    if update.message and update.message.text:
        if update.effective_chat.type != "private":
            return

        url_recebida = update.message.text
        chat_id = update.effective_chat.id

        if not url_recebida.startswith("http"):
            await update.message.reply_text("⚠️ Envie um link válido de produto (Shopee ou Mercado Livre).")
            return

        mensagem_aguarde = await update.message.reply_text("🔍 Analisando produto e gerando copy de vendas com IA...")

        try:
            prompt = f"""
            Você é um especialista em vendas de afiliados para Telegram e WhatsApp.
            Com base neste link de produto: {url_recebida}
            Crie uma postagem altamente persuasiva contendo:
            1. Título chamativo com emojis.
            2. Indicação de preço/desconto atraente.
            3. Chamada para ação (CTA) para garantir no link.
            4. O link de afiliado fornecido ({url_recebida}) colado no final.
            Mantenha limpo, usando negrito (*texto*) e emojis. Não invente valores absurdos, foque em estruturar o texto perfeitamente.
            """

            response = client_ai.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )

            copy_gerada = response.text
            temporario_copys[chat_id] = copy_gerada

            teclado = [
                [
                    InlineKeyboardButton("✅ Aprovar e Postar no Canal", callback_data="aprovar"),
                    InlineKeyboardButton("❌ Descartar", callback_data="cancelar")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(teclado)

            await telegram_app.bot.delete_message(chat_id=chat_id, message_id=mensagem_aguarde.message_id)
            await update.message.reply_text(
                text=f"📋 **PRÉVIA DA POSTAGEM:**\n\n{copy_gerada}\n\n*O que deseja fazer?*",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Erro ao processar com a IA: {str(e)}")

def registrar_webhook_telegram():
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL}/{TELEGRAM_TOKEN}"
        url_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}"
        try:
            r = requests.get(url_api)
            print(f"Webhook configurado: {r.text}")
        except Exception as e:
            print(f"Erro ao registrar webhook: {e}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    registrar_webhook_telegram()
    app_flask.run(host='0.0.0.0', port=port)
    
