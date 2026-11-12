import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from deep_translator import GoogleTranslator

# Configuração de Logs
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Leitura das Variáveis de Ambiente
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BITLY_TOKEN = os.getenv("BITLY_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CANAL_DESTINO = os.getenv("CANAL_DESTINO", "-1003975825755")

# Whitelist de Segurança
WHITELIST = [5336222205, 6593135327]

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
            return f"👉 **CLIQUE AGORA PARA GARANTIR O SEU, E NAO FICAR SEM OFERTAS COMO ESSA É SÓ NO RADAR DO DESCONTO**\n🔗 {link_encurtado}"
    except Exception as e:
        logger.error(f"Erro ao encurtar link no Bitly: {e}")
    
    return url_longa

def traduzir_para_portugues(texto: str) -> str:
    """Traduz automaticamente qualquer texto em inglês para o português."""
    if not texto.strip():
        return texto
    try:
        tradutor = GoogleTranslator(source='auto', target='pt')
        texto_traduzido = tradutor.translate(texto)
        return texto_traduzido if texto_traduzido else texto
    except Exception as e:
        logger.error(f"Erro ao traduzir texto: {e}")
        return texto

def processar_com_gemini(texto_base: str) -> str:
    """Opcional: Processa a copy via Gemini se a chave estiver ativa e o usuário escolher."""
    if not GEMINI_API_KEY:
        return texto_base
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Melhore esta copy para alta conversão em vendas de afiliados, mantendo persuasiva e direta: {texto_base}"
        )
        if response and response.text:
            return response.text
    except Exception as e:
        logger.error(f"Erro na IA do Gemini (Modo Opcional): {e}")
    return texto_base

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in WHITELIST:
        await update.message.reply_text("⛔ Acesso restrito.")
        return

    await update.message.reply_text(
        "🔥 **Drika Híbrida & Tradutora Ativa!**\n\n"
        "Envie a FOTO + COPY + LINK. Textos em inglês serão traduzidos automaticamente."
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

    # Guarda os dados brutos na sessão do usuário temporariamente
    context.user_data['raw_input'] = {
        "text": raw_text or "",
        "photo_id": message.photo[-1].file_id if has_photo else None
    }

    # Menu interativo de escolha de processamento
    keyboard = [
        [
            InlineKeyboardButton("🤖 Usar IA (Gemini)", callback_data="mode_ai"),
            InlineKeyboardButton("⚡ Enviar Direto (Tradução + Bitly)", callback_data="mode_direct")
        ],
        [
            InlineKeyboardButton("❌ Descartar", callback_data="cancel_ok")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        "⚙️ **Como deseja processar esta postagem?**\n\n"
        "• **🤖 Usar IA:** Traduz (se necessário) e otimiza a copy.\n"
        "• **⚡ Enviar Direto:** Traduz o texto, aplica o Bitly direto (Ultrarrápido).",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in WHITELIST:
        await query.answer("Acesso não autorizado.", show_alert=True)
        return

    await query.answer()
    data = query.data
    raw_data = context.user_data.get('raw_input')

    if data in ["mode_ai", "mode_direct"]:
        if not raw_data:
            await query.edit_message_text("⚠️ Dados expirados. Envie o post novamente.")
            return

        raw_text = raw_data["text"]
        photo_id = raw_data["photo_id"]

        # Extrai link e traduz o restante do texto automaticamente para o português
        palavras = raw_text.split() if raw_text else []
        link_original = next((p for p in palavras if p.startswith("http")), "")
        link_final = encurtar_link_bitly(link_original) if link_original else ""
        
        texto_sem_link = raw_text.replace(link_original, "").strip() if link_original else (raw_text or "")
        texto_traduzido = traduzir_para_portugues(texto_sem_link)

        # Se escolheu IA, otimiza a copy traduzida
        if data == "mode_ai":
            try:
                texto_traduzido = processar_com_gemini(texto_traduzido)
            except Exception:
                pass 

        if link_final:
            legenda_final = f"{texto_traduzido}\n\n{link_final}".strip()
        else:
            legenda_final = texto_traduzido

        # Salva o post final pronto para aprovação
        context.user_data['pending_post'] = {
            "text": legenda_final,
            "photo_id": photo_id
        }

        # Botões de Aprovação Final
        keyboard = [
            [
                InlineKeyboardButton("🚀 Enviar para Rascunho", callback_data="send_ok"),
                InlineKeyboardButton("❌ Descartar", callback_data="cancel_ok")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.message.delete()
        except Exception:
            pass

        if photo_id:
            await context.bot.send_photo(chat_id=user_id, photo=photo_id, caption=legenda_final, reply_markup=reply_markup)
        else:
            await context.bot.send_message(chat_id=user_id, text=legenda_final, reply_markup=reply_markup)

    elif data == "send_ok":
        post_data = context.user_data.get('pending_post')
        if post_data:
            try:
                # Envia para o canal de rascunho
                if post_data["photo_id"]:
                    await context.bot.send_photo(chat_id=CANAL_DESTINO, photo=post_data["photo_id"], caption=post_data["text"])
                else:
                    await context.bot.send_message(chat_id=CANAL_DESTINO, text=post_data["text"])
                
                # Deleta a mensagem do PV limpando o histórico
                await query.message.delete()
                context.user_data.clear()
            except Exception as e:
                logger.error(f"Erro ao enviar para o canal: {e}")
                await query.message.reply_text(f"❌ Erro ao enviar para o rascunho: {e}")
        else:
            await query.message.reply_text("⚠️ Postagem expirada.")

    elif data == "cancel_ok":
        context.user_data.clear()
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
