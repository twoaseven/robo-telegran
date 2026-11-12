import os
import io
import logging
import requests
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from google import genai

# Configuração de Logs
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Leitura das Variáveis de Ambiente
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BITLY_TOKEN = os.getenv("BITLY_TOKEN")
CANAL_DESTINO = os.getenv("CANAL_DESTINO", "-1003975825755")  # Grupo de Rascunho

# Whitelist de Segurança (IDs autorizados)
WHITELIST = [5336222205, 6593135327]  # Cabral e Jade

# Inicialização do Cliente Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# Dicionário temporário para guardar postagens
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

SYSTEM_PROMPT = (
    "Atue como um copywriter especialista em canais de ofertas relâmpago no Telegram e WhatsApp. "
    "Sua missão é criar uma copy CURTA, magnética e de ALTÍSSIMA CONVERSÃO.\n\n"
    "REGRAS:\n"
    "1. Use gatilhos fortes de escassez e urgência (ex: 'Preço bugado', 'Últimas unidades', 'Corre antes que acabe').\n"
    "2. Foque no benefício principal em no máximo 2 linhas curtas.\n"
    "3. Destaque o PREÇO em negrito e caixa alta.\n"
    "4. Seja direto, sem introduções e sem enrolação. Entregue apenas o texto pronto para a legenda."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in WHITELIST:
        await update.message.reply_text("⛔ Acesso restrito.")
        return

    await update.message.reply_text(
        "🔥 **Drika Ajustada e Pronta!**\n\n"
        "Envie a **FOTO** com o preço e o link na legenda para gerar a copy enxuta com link do Bitly."
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

    status_msg = await message.reply_text("⚡ Gerando copy e encurtando link...")

    try:
        # Extrai o link do texto/legenda para mandar pro Bitly
        palavras = raw_text.split() if raw_text else []
        link_original = next((p for p in palavras if p.startswith("http")), "")
        link_final = encurtar_link_bitly(link_original) if link_original else ""

        contents = []
        photo_file_id = None

        if has_photo:
            photo_obj = message.photo[-1]
            photo_file_id = photo_obj.file_id
            tg_file = await context.bot.get_file(photo_file_id)
            img_bytes = await tg_file.download_as_bytearray()
            pil_image = Image.open(io.BytesIO(img_bytes))
            contents.append(pil_image)

        user_instruction = f"{SYSTEM_PROMPT}\n\nDados da oferta fornecidos:\n{raw_text}"
        contents.append(user_instruction)

        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=contents,
        )
        copy_text = response.text.strip()

        # Monta a legenda final unindo a copy da IA + o link encurtado limpo
        legenda_final = f"{copy_text}\n\n{link_final}" if link_final else copy_text

        post_id = str(message.message_id)
        pending_posts[post_id] = {
            "text": legenda_final,
            "photo_id": photo_file_id
        }

        keyboard = [
            [
                InlineKeyboardButton("🚀 Enviar para Rascunho", callback_data=f"send_{post_id}"),
                InlineKeyboardButton("❌ Descartar", callback_data=f"cancel_{post_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await status_msg.delete()

        if photo_file_id:
            await message.reply_photo(photo=photo_file_id, caption=legenda_final, reply_markup=reply_markup)
        else:
            await message.reply_text(text=legenda_final, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao processar: {e}")
        await status_msg.edit_text(f"❌ Erro ao processar. Detalhe: {e}")

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
                if post_data["photo_id"]:
                    await context.bot.send_photo(chat_id=CANAL_DESTINO, photo=post_data["photo_id"], caption=post_data["text"])
                    await query.edit_message_caption(caption=f"{post_data['text']}\n\n✅ **Enviado para o Rascunho!**")
                else:
                    await context.bot.send_message(chat_id=CANAL_DESTINO, text=post_data["text"])
                    await query.edit_message_text(text=f"{post_data['text']}\n\n✅ **Enviado para o Rascunho!**")
                
                del pending_posts[post_id]
            except Exception as e:
                logger.error(f"Erro ao enviar para o canal: {e}")
                await query.message.reply_text("❌ Erro ao enviar para o grupo de rascunho.")
        else:
            await query.message.reply_text("⚠️ Esta postagem expirou.")

    elif data.startswith("cancel_"):
        post_id = data.split("_")[1]
        if post_id in pending_posts:
            del pending_posts[post_id]
        if query.message.photo:
            await query.edit_message_caption(caption="❌ **Postagem descartada.**")
        else:
            await query.edit_message_text(text="❌ **Postagem descartada.**")

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
