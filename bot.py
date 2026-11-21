import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from deep_translator import GoogleTranslator

# Configuração de Logs
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Variáveis de Ambiente
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CANAL_DESTINO = os.getenv("CANAL_DESTINO", "-1003975825755")

# Whitelist de Segurança
WHITELIST = [5336222205, 6593135327]

# Etapas do fluxo
STEP_MEDIA_LINK = "media_link"
STEP_COPY = "copy"
STEP_SPECS = "specs"
STEP_CONFIRM = "confirm"

AVISO_SITE_MARKETPLACE = (
    "ℹ️ Informações técnicas completas do produto disponíveis diretamente no site do marketplace."
)


def traduzir_para_portugues(texto: str) -> str:
    """Traduz automaticamente o texto para o português."""
    if not texto or not texto.strip():
        return ""
    try:
        tradutor = GoogleTranslator(source="auto", target="pt")
        traduzido = tradutor.translate(texto.strip())
        return traduzido if traduzido else texto.strip()
    except Exception as e:
        logger.error(f"Erro ao traduzir texto: {e}")
        return texto.strip()


def extrair_link(texto: str) -> str:
    """Extrai o primeiro link HTTP/HTTPS encontrado no texto."""
    if not texto:
        return ""
    for palavra in texto.split():
        limpa = palavra.strip("<>()[]\"'")
        if limpa.startswith("http://") or limpa.startswith("https://"):
            return limpa
    return ""


def montar_legenda_final(draft: dict) -> str:
    """Monta a estrutura final conforme as etapas preenchidas."""
    link = draft.get("link", "").strip()
    copy_pt = draft.get("copy_pt", "").strip()
    specs_pt = draft.get("specs_pt", "").strip()

    bloco_specs = specs_pt if specs_pt else AVISO_SITE_MARKETPLACE
    cta_bloco = (
        f"👉 **CLIQUE AGORA PARA GARANTIR O SEU, E NAO FICAR SEM OFERTAS COMO ESSA É SÓ NO RADAR DO DESCONTO**\n"
        f"🔗 {link}"
    )

    partes = []
    if link:
        partes.append(link)
    if copy_pt:
        partes.append(copy_pt)
    if link:
        partes.append(cta_bloco)
    partes.append(f"📋 **Detalhes do produto:**\n{bloco_specs}")
    if link:
        partes.append(f"🔗 {link}")

    return "\n\n".join(partes).strip()


def iniciar_novo_rascunho(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = STEP_MEDIA_LINK
    context.user_data["draft"] = {
        "photo_id": None,
        "link": "",
        "copy_pt": "",
        "specs_pt": "",
    }
    context.user_data["temp_msg_ids"] = []


def registrar_msg_temp(context: ContextTypes.DEFAULT_TYPE, msg_id: int | None):
    if msg_id:
        msgs = context.user_data.setdefault("temp_msg_ids", [])
        if msg_id not in msgs:
            msgs.append(msg_id)


async def limpar_temporarias(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    msgs = context.user_data.get("temp_msg_ids", [])
    for mid in msgs:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass
    context.user_data["temp_msg_ids"] = []


def teclado_cancelar() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancelar", callback_data="cancel_flow")]]
    )


def teclado_specs() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⏩ Sem infos técnicas (usar aviso do site)",
                    callback_data="skip_specs",
                )
            ],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel_flow")],
        ]
    )


def teclado_confirmacao() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🚀 Enviar para Rascunho", callback_data="send_draft"),
                InlineKeyboardButton("❌ Cancelar", callback_data="cancel_flow"),
            ]
        ]
    )


async def enviar_preview_final(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    draft = context.user_data.get("draft", {})
    legenda = montar_legenda_final(draft)
    context.user_data["step"] = STEP_CONFIRM
    context.user_data["final_caption"] = legenda

    photo_id = draft.get("photo_id")
    if photo_id:
        enviada = await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo_id,
            caption=legenda,
            reply_markup=teclado_confirmacao(),
        )
    else:
        enviada = await context.bot.send_message(
            chat_id=chat_id,
            text=legenda,
            reply_markup=teclado_confirmacao(),
        )
    registrar_msg_temp(context, enviada.message_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in WHITELIST:
        await update.message.reply_text("⛔ Acesso restrito.")
        return

    iniciar_novo_rascunho(context)
    msg = await update.message.reply_text(
        "🔥 **Drika em Modo Etapas Ativa!**\n\n"
        "**Etapa 1/3:** Envie a **IMAGEM** e o **LINK DE AFILIADO** do produto.",
        reply_markup=teclado_cancelar(),
    )
    registrar_msg_temp(context, msg.message_id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in WHITELIST:
        return

    message = update.message
    chat_id = message.chat_id
    registrar_msg_temp(context, message.message_id)

    if "step" not in context.user_data:
        iniciar_novo_rascunho(context)

    step = context.user_data.get("step")
    draft = context.user_data.setdefault(
        "draft", {"photo_id": None, "link": "", "copy_pt": "", "specs_pt": ""}
    )

    has_photo = bool(message.photo)
    raw_text = (message.caption if has_photo else message.text) or ""

    if step == STEP_MEDIA_LINK:
        if has_photo:
            draft["photo_id"] = message.photo[-1].file_id

        link_encontrado = extrair_link(raw_text)
        if link_encontrado:
            draft["link"] = link_encontrado

        if not draft["photo_id"] and not draft["link"]:
            aviso = await message.reply_text(
                "⚠️ Envie a **imagem** e o **link de afiliado** (juntos ou um após o outro).",
                reply_markup=teclado_cancelar(),
            )
            registrar_msg_temp(context, aviso.message_id)
            return

        if draft["photo_id"] and not draft["link"]:
            aviso = await message.reply_text(
                "✅ Imagem recebida! Agora envie o **link de afiliado**.",
                reply_markup=teclado_cancelar(),
            )
            registrar_msg_temp(context, aviso.message_id)
            return

        if draft["link"] and not draft["photo_id"]:
            aviso = await message.reply_text(
                "✅ Link recebido! Agora envie a **imagem** do produto.",
                reply_markup=teclado_cancelar(),
            )
            registrar_msg_temp(context, aviso.message_id)
            return

        # Ambos recebidos -> avança para Etapa 2 (Copy)
        context.user_data["step"] = STEP_COPY
        prox = await message.reply_text(
            "✅ Estrutura base montada com imagem e link.\n\n"
            "**Etapa 2/3:** Agora envie a **COPY** do produto (traduzo automaticamente para o português).",
            reply_markup=teclado_cancelar(),
        )
        registrar_msg_temp(context, prox.message_id)

    elif step == STEP_COPY:
        if not raw_text.strip():
            aviso = await message.reply_text(
                "⚠️ Envie o texto da **copy** do produto para continuar.",
                reply_markup=teclado_cancelar(),
            )
            registrar_msg_temp(context, aviso.message_id)
            return

        # Caso o usuário inclua o link junto na copy, remove o link duplicado da copy
        link_atual = draft.get("link", "")
        texto_copy = raw_text.replace(link_atual, "").strip() if link_atual else raw_text.strip()
        draft["copy_pt"] = traduzir_para_portugues(texto_copy)

        context.user_data["step"] = STEP_SPECS
        prox = await message.reply_text(
            "✅ Copy encaixada na estrutura.\n\n"
            "**Etapa 3/3:** Envie as **INFORMAÇÕES TÉCNICAS** do produto, se houver — "
            "ou clique no botão abaixo para usar a orientação padrão do site do marketplace.",
            reply_markup=teclado_specs(),
        )
        registrar_msg_temp(context, prox.message_id)

    elif step == STEP_SPECS:
        if raw_text.strip():
            draft["specs_pt"] = traduzir_para_portugues(raw_text.strip())
        else:
            draft["specs_pt"] = AVISO_SITE_MARKETPLACE

        await enviar_preview_final(update, context, chat_id)

    elif step == STEP_CONFIRM:
        aviso = await message.reply_text(
            "👆 Use **Enviar para Rascunho** ou **Cancelar** na prévia atual para iniciar uma nova.",
            reply_markup=teclado_confirmacao(),
        )
        registrar_msg_temp(context, aviso.message_id)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if user_id not in WHITELIST:
        await query.answer("Acesso não autorizado.", show_alert=True)
        return

    await query.answer()
    data = query.data
    chat_id = query.message.chat_id

    if data == "cancel_flow":
        registrar_msg_temp(context, query.message.message_id)
        await limpar_temporarias(context, chat_id)
        iniciar_novo_rascunho(context)
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text="🗑️ Fluxo cancelado.\n\n**Etapa 1/3:** Envie a **IMAGEM** e o **LINK DE AFILIADO** para começar de novo.",
            reply_markup=teclado_cancelar(),
        )
        registrar_msg_temp(context, msg.message_id)

    elif data == "skip_specs":
        draft = context.user_data.setdefault("draft", {})
        draft["specs_pt"] = AVISO_SITE_MARKETPLACE
        registrar_msg_temp(context, query.message.message_id)
        await enviar_preview_final(update, context, chat_id)

    elif data == "send_draft":
        draft = context.user_data.get("draft", {})
        legenda = context.user_data.get("final_caption") or montar_legenda_final(draft)
        photo_id = draft.get("photo_id")

        if not legenda:
            await query.message.reply_text("⚠️ Nenhum rascunho pronto para envio.")
            return

        try:
            if photo_id:
                await context.bot.send_photo(
                    chat_id=CANAL_DESTINO,
                    photo=photo_id,
                    caption=legenda,
                )
            else:
                await context.bot.send_message(
                    chat_id=CANAL_DESTINO,
                    text=legenda,
                )

            registrar_msg_temp(context, query.message.message_id)
            await limpar_temporarias(context, chat_id)
            iniciar_novo_rascunho(context)

            confirm = await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Enviado para o rascunho! Pronto para o próximo — envie **IMAGEM** e **LINK**.",
                reply_markup=teclado_cancelar(),
            )
            registrar_msg_temp(context, confirm.message_id)

        except Exception as e:
            logger.error(f"Erro ao enviar para o canal de rascunho: {e}")
            await query.message.reply_text(f"❌ Erro ao enviar para o rascunho: {e}")


def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler((filters.PHOTO | filters.TEXT) & ~filters.COMMAND, handle_message)
    )
    application.add_handler(CallbackQueryHandler(button_handler))

    PORT = int(os.environ.get("PORT", "10000"))
    RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL.strip()}/{TELEGRAM_TOKEN}"
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_TOKEN,
            webhook_url=webhook_url,
        )
    else:
        application.run_polling()


if __name__ == "__main__":
    main()
