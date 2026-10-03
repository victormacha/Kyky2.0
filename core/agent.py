"""Laço do agente: o modelo pede uma ferramenta -> executa -> devolve o resultado, até responder.
Tem memória de trabalho (ferramenta 'anotar') e empurra o modelo a CONCLUIR antes de acabarem os passos."""
import json
from . import tools


def _compactar(messages, limite=20000):
    """Encurta resultados antigos de ferramentas quando a conversa fica grande (provedores gratuitos têm limite)."""
    if sum(len(m.get("content") or "") for m in messages) <= limite:
        return
    for m in messages[:-6]:
        if m.get("role") == "tool" and len(m.get("content") or "") > 1200:
            m["content"] = m["content"][:1200] + "\n[... resultado antigo resumido para economizar espaço]"


def _com_notas(messages):
    """Cópia da conversa com as anotações do próprio agente fixadas no topo (não se perdem na compactação)."""
    if not tools.NOTAS:
        return messages
    fixa = {"role": "system", "content": "SUAS ANOTAÇÕES ATÉ AGORA (não releia o que já está aqui):\n- " + "\n- ".join(tools.NOTAS)}
    return messages[:1] + [fixa] + messages[1:]


def run(brain, messages, level, confirm, max_steps=8, on_tool=None, specs=None):
    provider = None
    tools.NOTAS.clear()
    for passo in range(max_steps):
        _compactar(messages)
        restantes = max_steps - passo
        ferramentas = specs or tools.SPECS
        if max_steps >= 15 and restantes == 6:
            messages.append({"role": "user", "content": "Aviso: restam poucos passos. Pare de explorar, anote o que já sabe e "
                             "conclua: causa provável (arquivo e linhas), correção proposta e o que ficou sem confirmar."})
        if restantes == 1:
            ferramentas = None      # último passo: obrigado a responder em texto
            messages.append({"role": "user", "content": "Responda agora, em texto, com o que descobriu até aqui: "
                             "causa (arquivo e linhas), correção proposta e o que não deu para confirmar. Seja honesto."})
        msg, provider = brain.chat(_com_notas(messages), level, tools=ferramentas)
        if not msg.tool_calls:
            return msg.content or "", provider
        chamadas = []
        for tc in msg.tool_calls:
            item = {"id": tc.id, "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            extra = (getattr(tc, "model_extra", None) or {}).get("extra_content")   # Gemini 3: assinatura do raciocínio
            if extra:
                item["extra_content"] = extra
            chamadas.append(item)
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": chamadas})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = None
            if args is None:
                result = "erro: argumentos inválidos (JSON malformado), tente de novo"
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                continue
            print(f"  [ferramenta] {tc.function.name} {args.get('path') or args.get('query') or args.get('url') or ''}")
            if on_tool:
                on_tool(tc.function.name, args)
            result = tools.execute(tc.function.name, args, confirm)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    return "Parei: passos demais sem chegar a uma resposta.", provider
