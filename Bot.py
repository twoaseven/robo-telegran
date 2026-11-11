import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from google import genai

# --- CONFIGURAÇÕES DE AMBIENTE (Puxadas do Render) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Exemplo: "@RadarDo_Desconto" ou o ID numérico do canal
CANAL_DESTINO = os.getenv("CANAL_DESTINO", "@RadarDo_Desconto")

# Inicializa o cliente do Gemini
client_ai = genai.Client(api_key=GEMINI_API_KEY)

# Configuração de logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Dicionário temporário para guardar a copy gerada aguardando aprovação
temporario_copys = {}

async def processar_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Garante que só responde no chat privado (PV) com você
    if update.effective_chat.type != "private":
        return

    url_recebida = update.message.text
    chat_id = update.effective_chat.id

    if not url_recebida.startswith("http"):
        await update.message.reply_text("⚠️ Envie um link válido de produto da Shopee ou Mercado Livre.")
        return

    mensagem_aguarde = await update.message.reply_text("🔍 Analisando produto e gerando copy de vendas com IA...")

    try:
        # Prompt técnico voltado para conversão em e-commerce
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

        # Salva temporariamente vinculada ao seu chat_id
        temporario_copys[chat_id] = copy_gerada

        # Cria os botões de controle de aprovação
        teclado = [
            [
                InlineKeyboardButton("✅ Aprovar e Postar no Canal", callback_data="aprovar"),
                InlineKeyboardButton("❌ Descartar", callback_data="cancelar")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(teclado)

        # Deleta a mensagem de "aguarde" e envia a prévia com os botões
        await context.bot.delete_message(chat_id=chat_id, message_id=mensagem_aguarde.message_id)
        
        await update.message.reply_text(
            text=f"📋 **PRÉVIA DA POSTAGEM:**\n\n{copy_gerada}\n\n*O que deseja fazer?*",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao processar com a IA: {str(e)}")

async def BotoesAprovacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    acao = query.data

    if acao == "aprovar":
        copy_pronta = temporario_copys.get(chat_id)
        if not copy_pronta:
            await query.edit_message_text("⚠️ Nenhuma copy pendente encontrada.")
            return

        # Envia de fato para o canal público do Telegram
        try:
            await context.bot.send_message(
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
        
    # Limpa o cache temporário
    if chat_id in temporario_copys:
        del temporario_copys[chat_id]

def main():
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        print("Erro: As variáveis de ambiente TELEGRAM_TOKEN e GEMINI_API_KEY precisam estar configuradas.")
        return

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Handler para mensagens de texto (links enviados no PV)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), processar_link))
    
    # Handler para o clique nos botões de aprovação
    app.add_handler(CallbackQueryHandler(BotoesAprovacao))

    print("🤖 Robô de ofertas pronto e operando...")
    app.run_polling()

if __name__ == '__main__':
    main()
  
