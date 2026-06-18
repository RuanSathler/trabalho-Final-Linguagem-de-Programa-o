#!/usr/bin/env python3
"""Implementação de mini-Fire."""
import sys
import sys
import inspect
import importlib.util
import os

def parse_bool(valor_str):
    """Converte strings em valores booleanos conforme a especificação."""
    if isinstance(valor_str, bool):
        return valor_str
    val = valor_str.lower()
    if val in ('true', 'yes', '1'):
        return True
    if val in ('false', 'no', '0'):
        return False
    raise ValueError("booleano inválido")

def exibe_ajuda_geral(caminho_modulo, modulo, funcoes_cli):
    """Gera o menu de ajuda geral listando todos os comandos."""
    print(f"\nMódulo: {os.path.basename(caminho_modulo)}")
    doc_modulo = inspect.getdoc(modulo)
    if doc_modulo:
        print(f"Descrição: {doc_modulo.splitlines()[0]}\n")
    else:
        print("Descrição: Módulo sem descrição.\n")

    print("Comandos disponíveis:")
    for nome, func in funcoes_cli.items():
        doc_func = inspect.getdoc(func)
        desc = doc_func.splitlines()[0] if doc_func else "Sem descrição."
        print(f"  {nome:<6} - {desc}")

        print("  Parâmetros:")
        sig = inspect.signature(func)
        for param_nome, param in sig.parameters.items():
            tipo_str = param.annotation.__name__ if param.annotation != inspect.Parameter.empty else "str"
            if param.default == inspect.Parameter.empty:
                detalhe = "obrigatório"
            else:
                detalhe = f"padrão={param.default}"
            print(f"      --{param_nome} ({tipo_str}, {detalhe})")
        print()

def exibe_ajuda_comando(nome_comando, func):
    """Gera o menu de ajuda específico para um único comando."""
    doc_func = inspect.getdoc(func)
    desc = doc_func.splitlines()[0] if doc_func else "Sem descrição."
    print(f"\nComando: {nome_comando}")
    print(f"Descrição: {desc}\n")

    sig = inspect.signature(func)
    uso_args = []

    for param_nome, param in sig.parameters.items():
        tipo_str = param.annotation.__name__ if param.annotation != inspect.Parameter.empty else "STR"
        if param.default == inspect.Parameter.empty:
            uso_args.append(f"--{param_nome} {tipo_str.upper()}")
        else:
            uso_args.append(f"[--{param_nome} {tipo_str.upper()}]")

    print(f"Uso: {nome_comando} {' '.join(uso_args)}\n")

    print("Parâmetros:")
    for param_nome, param in sig.parameters.items():
        tipo_str = param.annotation.__name__ if param.annotation != inspect.Parameter.empty else "str"
        if param.default == inspect.Parameter.empty:
            detalhe = "obrigatório"
        else:
            detalhe = f"padrão={param.default}"
        print(f"  --{param_nome} ({tipo_str}, {detalhe})")

    # Tenta extrair a anotação de retorno
    retorno_str = sig.return_annotation.__name__ if sig.return_annotation != inspect.Signature.empty else "Qualquer"
    print(f"\nRetorna: {retorno_str}\n")

def meu_fire(caminho_modulo):
    if not os.path.isfile(caminho_modulo):
        print(f"Erro: Arquivo '{caminho_modulo}' não encontrado")
        sys.exit(1)

    # 1. Carrega o módulo dinamicamente
    nome_modulo = os.path.splitext(os.path.basename(caminho_modulo))[0]
    spec = importlib.util.spec_from_file_location(nome_modulo, caminho_modulo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    # 2. Identifica funções no nível global do módulo
    funcoes_cli = {}
    for nome, obj in inspect.getmembers(modulo, inspect.isfunction):
        # Ignora funções importadas de outros módulos (garante que pertence a este ficheiro)
        if obj.__module__ == nome_modulo: 
            funcoes_cli[nome] = obj

    args_cli = sys.argv[2:]

    # 3. Tratamento de Ajuda Geral
    if not args_cli or args_cli[0] in ('--help', 'ajuda', '-h'):
        exibe_ajuda_geral(caminho_modulo, modulo, funcoes_cli)
        return

    comando = args_cli[0]

    # Tratamento de Erro: Função inexistente
    if comando not in funcoes_cli:
        print(f"Erro: Comando '{comando}' não encontrado. Use --help para listar.")
        sys.exit(1)

    func = funcoes_cli[comando]

    # 4. Tratamento de Ajuda Específica do Comando
    if len(args_cli) > 1 and args_cli[1] in ('--help', 'ajuda', '-h'):
        exibe_ajuda_comando(comando, func)
        return

    sig = inspect.signature(func)
    params = list(sig.parameters.values())
    kwargs_para_chamar = {}

    # 5. Parsing de Argumentos da Linha de Comandos
    i = 1
    args_fornecidos = []
    kwargs_fornecidos = {}

    while i < len(args_cli):
        arg = args_cli[i]
        if arg.startswith("--"):
            chave = arg[2:]
            # Verifica se é uma flag booleana sem valor seguinte
            if i + 1 < len(args_cli) and not args_cli[i+1].startswith("--"):
                kwargs_fornecidos[chave] = args_cli[i+1]
                i += 2
            else:
                kwargs_fornecidos[chave] = "FLAG_BOOLEANA_SEM_VALOR"
                i += 1
        else:
            args_fornecidos.append(arg)
            i += 1

    # Mapeamento e Validação de Tipos
    idx_pos = 0
    for param in params:
        nome = param.name
        valor_bruto = None

        # Atribui valor se foi passado de forma posicional
        if idx_pos < len(args_fornecidos):
            valor_bruto = args_fornecidos[idx_pos]
            idx_pos += 1
        # Atribui valor se foi passado de forma nomeada (--chave)
        elif nome in kwargs_fornecidos:
            valor_bruto = kwargs_fornecidos.pop(nome)

        if valor_bruto is not None:
            # Conversão dinâmica de tipos
            tipo_esperado = param.annotation

            # Se for uma flag sem valor, trata como booleano inverso ao padrão
            if valor_bruto == "FLAG_BOOLEANA_SEM_VALOR":
                if tipo_esperado == bool or isinstance(param.default, bool):
                    # Se o padrão é False, a presença da flag torna-o True
                    kwargs_para_chamar[nome] = not param.default if isinstance(param.default, bool) else True
                else:
                    print(f"Erro: Parâmetro '{nome}' requer um valor.")
                    sys.exit(1)
                continue

            try:
                if tipo_esperado == int:
                    kwargs_para_chamar[nome] = int(valor_bruto)
                elif tipo_esperado == float:
                    kwargs_para_chamar[nome] = float(valor_bruto)
                elif tipo_esperado == bool or isinstance(param.default, bool):
                    kwargs_para_chamar[nome] = parse_bool(valor_bruto)
                else:
                    kwargs_para_chamar[nome] = valor_bruto # Padrão string
            except ValueError:
                nome_tipo = tipo_esperado.__name__ if hasattr(tipo_esperado, '__name__') else 'valor válido'
                print(f"Erro: Parâmetro '{nome}' esperava {nome_tipo}, recebeu '{valor_bruto}'")
                sys.exit(1)
        else:
            # Erro: Argumento obrigatório em falta
            if param.default == inspect.Parameter.empty:
                print(f"Erro: Função '{comando}' requer o parâmetro obrigatório '{nome}'")
                sys.exit(1)

    # Erro: Foram passados mais argumentos posicionais do que a função aceita
    if idx_pos < len(args_fornecidos):
        print(f"Erro: Função '{comando}' requer {len(params)} argumentos, mas recebeu mais do que o esperado.")
        sys.exit(1)

    # 6. Executar a função!
    func(**kwargs_para_chamar)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python meu_fire.py <arquivo.py> [comando] [args...]")
        sys.exit(1)

    meu_fire(sys.argv[1])
