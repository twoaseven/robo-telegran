import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Configuração de Logs
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Leitura das Variáveis de Ambiente
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BITLY_TOKEN = os.getenv("BITLY_TOKEN")
CANAL_DESTINO = os.getenv("CANAL_DESTINO", "-1003975825755")  # Grupo de Rascunho

# Whitelist de Segurança (IDs autorizados)
WHITELIST = [5336222205, 6593135327]  # Cabral e Jade

# Dicionário temporário para guardar postagens pendentes
pending_posts = {}

def encurtar_link_bitly(url_longa: str) -> str:
    """Encurta o link usando a API do Bitly e aplica o CTA limpo."""
    if not BITLY_TOKEN or not url_longa.startswith("http"):
        return url_longa

    headers = {
        "Authorization": f"Bearer {BITLY_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {"long_url": url_longa}
    
    try:
        response = requests.post("https://api-ssl.bitly.com/v4/shorten", json=data, headers=headers)
        if response.status_code in [200, 201]:
            link_encurtado = response.json().get("link")
            return f"👉 **CLIQUE AQUI PARA GARANTIR A OFERTA**\n🔗 {link_encurtado}"
    except Exception as e:
        logger.error(f"Erro ao encurtar link no Bitly: {e}")
    
    return url_longa

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in WHITELIST:
        await update.message.reply_text("⛔ Acesso restrito.")
        return

    await update.message.reply_text(
        "🔥 **Drika Modo Limpeza Ativa!**\n\n"
        "Envie a **FOTO PRONTA** com o link na legenda. "
        "Vou encurtar o link, mandar para o rascunho e **limpar o PV** assim que você aprovar."
    )

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in WHITELIST:
        return

    message = update.message
    has_photo = bool(message.photo)
    raw_text = message.caption if has_photo else message.text

    if not has_photo and not raw_text:
        return

    try:
        # Extrai o link do texto/legenda para mandar pro Bitly
        palavras = raw_text.split() if raw_text else []
        link_original = next((p for p in palavras if p.startswith("http")), "")
        link_final = encurtar_link_bitly(link_original) if link_original else ""

        # Remove o link longo original e adiciona o bloco limpo do Bitly
        texto_limpo = raw_text.replace(link_original, "").strip() if link_original else (raw_text or "")
        
        if link_final:
            legenda_final = f"{texto_limpo}\n\n{link_final}".strip()
        else:
            legenda_final = texto_limpo

        photo_file_id = message.photo[-1].file_id if has_photo else None

        post_id = str(message.message_id)
        pending_posts[post_id] = {
            "text": legenda_final,
            "photo_id": photo_file_id,
            "chat_id": message.chat_id
        }

        keyboard = [
            [
                InlineKeyboardButton("🚀 Enviar para Rascunho", callback_data=f"send_{post_id}"),
                InlineKeyboardButton("❌ Descartar", callback_data=f"cancel_{post_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if photo_file_id:
            await message.reply_photo(photo=photo_file_id, caption=legenda_final, reply_markup=reply_markup)
        else:
            await message.reply_text(text=legenda_final, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao processar: {e}")
        await message.reply_text(f"❌ Erro ao processar mensagem. Detalhe: {e}")

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
        post_data = pending_posts.get(post_id)

        if post_data:
            try:
                # 1. Envia para o canal de rascunho oficial
                if post_data["photo_id"]:
                    await context.bot.send_photo(chat_id=CANAL_DESTINO, photo=post_data["photo_id"], caption=post_data["text"])
                else:
                    await context.bot.send_message(chat_id=CANAL_DESTINO, text=post_data["text"])
                
                # 2. Deleta a mensagem de preview do chat privado (PV) para manter o histórico limpo
                await query.message.delete()
                
                # Remove da memória temporária
                del pending_posts[post_id]
            except Exception as e:
                logger.error(f"Erro ao enviar para o canal ou apagar mensagem: {e}")
                await query.message.reply_text("❌ Erro ao processar o envio para o rascunho.")
        else:
            await query.message.reply_text("⚠️ Esta postagem expirou.")

    elif data.startswith("cancel_"):
        post_id = data.split("_")[1]
        if post_id in pending_posts:
            del pending_posts[post_id]
        
        # Deleta a mensagem do PV se descartado também
        try:
            await query.message.delete()
        except Exception:
            pass

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler((filters.PHOTO | filters.TEXT) & ~filters.COMMAND, handle_input))
    application.add_handler(CallbackQueryHandler(button_handler))

    PORT = int(os.environ.get("PORT", "10000"))
    RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL.strip()}/{TELEGRAM_TOKEN}"
        logger.info(f"Iniciando Webhook em: {webhook_url}")
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
