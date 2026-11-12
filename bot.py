import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from google import genai

# Configuração de Logs
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Leitura das Variáveis de Ambiente
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CANAL_DESTINO = os.getenv("CANAL_DESTINO", "-1003975825755") # Grupo de Rascunho

# Whitelist de Segurança (IDs autorizados)
WHITELIST = [5336222205, 6593135327]  # Cabral e Jade

# Inicialização do Cliente Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# Dicionário temporário para guardar copys geradas aguardando aprovação
pending_posts = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in WHITELIST:
        await update.message.reply_text("⛔ Acesso restrito. Este robô é de uso exclusivo.")
        return
    
    await update.message.reply_text(
        "🤖 **Drika Ativa e Blindada!**\n\n"
        "Envie o link do produto (Amazon, Shopee, Mercado Livre, etc.) "
        "para eu gerar a copy de vendas estruturada."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in WHITELIST:
        return  # Ignora mensagens de usuários de fora silenciosamente

    text = update.message.text
    if not text:
        return

    await update.message.reply_text("⏳ Processando link e gerando copy...")

    try:
        prompt = (
            "Atue como especialista em copywriting de alta conversão para canais de ofertas no Telegram. "
            "Crie uma copy persuasiva, limpa e estruturada para o seguinte link/produto:\n\n"
            f"{text}\n\n"
            "Inclua emojis estratégicos, destaque o preço se houver e deixe o espaço para o link de afiliado."
        )

        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
        )
        copy_text = response.text

        # Armazena a copy temporariamente para envio posterior
        post_id = str(update.message.message_id)
        pending_posts[post_id] = copy_text

        # Cria botões de ação
        keyboard = [
            [
                InlineKeyboardButton("🚀 Enviar para Rascunho", callback_data=f"send_{post_id}"),
                InlineKeyboardButton("❌ Descartar", callback_data=f"cancel_{post_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"📝 **Copy Gerada com Sucesso:**\n\n{copy_text}",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Erro ao gerar copy: {e}")
        await update.message.reply_text("❌ Ocorreu um erro ao gerar a copy com a IA.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id not in WHITELIST:
        await query.answer("Acesso não autorizado.", show_alert=True)
        return

    await query.answer()
    data = query.data

    if data.startswith("send_"):
        post_id = data.split("_")[1]
        copy_text = pending_posts.get(post_id)

        if copy_text:
            try:
                # Envia direto para o Grupo Privado de Rascunho
                await context.bot.send_message(chat_id=CANAL_DESTINO, text=copy_text)
                await query.edit_message_text(text="✅ **Copy enviada com sucesso para o grupo de rascunho!**")
            except Exception as e:
                logger.error(f"Erro ao enviar para o canal: {e}")
                await query.edit_message_text(text="❌ Erro ao enviar para o canal de destino.")
        else:
            await query.edit_message_text(text="⚠️ Esta copy expirou ou já foi processada.")

    elif data.startswith("cancel_"):
        await query.edit_message_text(text="❌ **Copy descartada.**")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Executando via Webhook mapeado pelo Render
    PORT = int(os.environ.get("PORT", "10000"))
    RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL.strip()}/{TELEGRAM_TOKEN}"
        logger.info(o=f"Iniciando Webhook em: {webhook_url}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_TOKEN,
            webhook_url=webhook_url
        )
    else:
        application.run_polling()

if __name__ == "__main__":
    main()
    
