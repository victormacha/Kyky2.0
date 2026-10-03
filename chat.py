from pathlib import Path
from core.brain import Brain
from core import memory, agent, tools

BASE = Path(__file__).parent

TOOLS_HINT = (
    "\n\nVocê tem ferramentas para listar, ler e criar arquivos e rodar scripts Python numa pasta "
    "de trabalho (workspace), pesquisar na web e gerenciar a lista de tarefas do usuário (add_task, list_tasks, complete_task). Quando o usuário pedir um programa, crie o arquivo, rode para testar "
    "e corrija se der erro. Depois explique de forma curta o que fez."
)


def confirm(name, args):
    print("\n  A Kyky quer executar:", tools.describe(name, args))
    return input("  Permitir? [s/N] ").strip().lower() in ("s", "sim", "y")


def main():
    system = (BASE / "personality.md").read_text(encoding="utf-8") + TOOLS_HINT
    brain = Brain()
    level = "strong"
    history = memory.recent(20)
    print("Kyky pronta.  Comandos: /forte  /rapido  /sair")
    while True:
        try:
            text = input("\nvocê> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text == "/sair":
            break
        if text in ("/forte", "/rapido"):
            level = "strong" if text == "/forte" else "fast"
            print(f"modo: {level}")
            continue
        msgs = [{"role": "system", "content": system}] + history[-20:] + [{"role": "user", "content": text}]
        try:
            answer, who = agent.run(brain, msgs, level, confirm)
        except RuntimeError as e:
            print(e)
            continue
        history += [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]
        memory.save("user", text)
        memory.save("assistant", answer, who)
        print(f"\nkyky [{who}]> {answer}")


if __name__ == "__main__":
    main()
