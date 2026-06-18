"""Agente estratégico MEGA simples.
Marco Cristo, 2026

Objetivo desta versão:
- servir como ponto de partida;
- manter a interface esperada pela infraestrutura;
- ser funcional, para vcs terem um exemplo que roda.

Características:
- escolhe a carta do narrador por uma heurística muito simples;
- gera dica com a LLM, mas com prompt beeeem básico;
- escolhe carta e votos com regras ingênuas;
- não tenta otimizar de verdade para vencer o baseline aleatório.
"""
from __future__ import annotations

import argparse
import random
import re
import asyncio
import logging
from typing import Any, Dict, List

from base_agent import BaseAgent
from fasta2a import A2AApp, tool

app = A2AApp(name="LLMAgent")
LOGGER = logging.getLogger(__name__)

class LLMAgent(BaseAgent):
    def __init__(self, name: str, llm_url: str):
        # Aumentamos um pouco o timeout para dar tempo à LLM pensar
        super().__init__(name=name, llm_url=llm_url, request_timeout=60.0)
        self.hand = []

    # ---------------------------------------------------------
    # TOOL 1: Receber a mão
    # ---------------------------------------------------------
    @tool()
    async def receive_hand(self, hand: List[Dict[str, Any]]) -> Dict[str, Any]:
        self.hand = list(hand)
        return {"status": "ok", "hand_size": len(self.hand)}

    # ---------------------------------------------------------
    # TOOL 2: Escolher carta (NARRADOR)
    # ---------------------------------------------------------
    @tool()
    async def choose_card(self) -> Dict[str, Any]:
        """
        Estratégia: Escolher a carta que tenha o vocabulário mais rico.
        Músicas com mais palavras únicas são mais fáceis para gerar dicas que
        enganem uns e ajudem outros.
        """
        if not self.hand:
            raise RuntimeError("Mão vazia!")

        best_card = None
        best_score = -1

        for card in self.hand:
            words = set(self._normalize_words(card.get("lyrics", "")))
            score = len(words)
            if score > best_score:
                best_score = score
                best_card = card

        return {"chosen_card": best_card or random.choice(self.hand)}

    # ---------------------------------------------------------
    # TOOL 3: Dar a Dica (NARRADOR)
    # ---------------------------------------------------------
    @tool()
    async def send_clue(self, lyrics: str, max_words: int = 6) -> Dict[str, Any]:
        """
        Estratégia: Pedir à LLM para extrair o TEMA da música. 
        Se ela falhar ou der timeout, usamos um Fallback matemático.
        """
        prompt = (
            f"Leia a letra desta música brasileira:\n"
            f"\"{lyrics[:300]}...\"\n\n"
            f"Crie uma dica poética de no máximo {max_words} palavras que descreva o tema principal desta música. "
            f"NÃO copie frases exatas da letra. Responda APENAS com a dica e nada mais."
        )

        clue = ""
        try:
            # Tenta usar a IA
            resposta_llm = await asyncio.wait_for(
                self.llm_generate(prompt, max_tokens=15, temperature=0.7),
                timeout=40.0
            )
            
            # Limpeza pesada da resposta da IA
            clue = re.sub(r'["\'.:*_]', '', resposta_llm).strip()
            clue = " ".join(clue.split()[:max_words]) # Força o limite de palavras
            
        except Exception as e:
            LOGGER.warning(f"Falha na LLM ao gerar dica. Usando Fallback. Erro: {e}")
        
        # FALLBACK: Se a LLM retornar vazio, muito grande ou der erro
        if not clue or len(clue.split()) < 1 or len(clue.split()) > max_words:
            palavras_uteis = list(self._normalize_words(lyrics))
            random.shuffle(palavras_uteis)
            clue = " ".join(palavras_uteis[:3]) # Pega 3 palavras soltas da música

        return {"clue": clue}

    # ---------------------------------------------------------
    # TOOL 4: Escolher carta para BLEFAR (MELÔMANO)
    # ---------------------------------------------------------
    @tool()
    async def select_card_by_clue(self, clue: str) -> Dict[str, Any]:
        """
        Estratégia: Calcular a similaridade (sobreposição de palavras) entre
        a dica e as músicas da nossa mão. Usar a LLM para isso é muito lento
        e propenso a erro para o Phi-3.5. A matemática pura ganha aqui.
        """
        best_card = self.hand[0]
        best_score = -1.0

        clue_words = self._normalize_words(clue)

        for card in self.hand:
            song_words = self._normalize_words(card.get("lyrics", ""))
            title_words = self._normalize_words(card.get("title", ""))
            
            # Ganha pontos se bater com a letra
            overlap = len(clue_words.intersection(song_words))
            # Ganha bônus alto se bater com o título
            title_bonus = 2.0 if clue_words.intersection(title_words) else 0.0
            
            score = overlap + title_bonus
            
            if score > best_score:
                best_score = score
                best_card = card

        return {"chosen_card": best_card}

    # ---------------------------------------------------------
    # TOOL 5: Votar na carta do narrador (MELÔMANO)
    # ---------------------------------------------------------
    @tool()
    async def vote(self, clue: str, options: List[Dict[str, Any]], my_chosen_card: Dict[str, Any]) -> Dict[str, Any]:
        """
        Estratégia: Votar nas duas cartas da mesa que mais se parecem com a dica.
        Nunca votamos na nossa própria carta.
        """
        my_idx = -1
        scored_options = []
        clue_words = self._normalize_words(clue)

        for idx, card in enumerate(options):
            if card["id"] == my_chosen_card["id"]:
                my_idx = idx
                continue
                
            song_words = self._normalize_words(card.get("lyrics", ""))
            title_words = self._normalize_words(card.get("title", ""))
            
            overlap = len(clue_words.intersection(song_words))
            title_bonus = 2.0 if clue_words.intersection(title_words) else 0.0
            
            score = overlap + title_bonus
            scored_options.append((score, idx))

        # Ordena do maior score para o menor
        scored_options.sort(reverse=True, key=lambda x: x[0])

        # Pega os índices dos dois melhores (se houver)
        votes = [idx for score, idx in scored_options[:2]]

        # Fallback de segurança garantida
        if len(votes) < 2:
            for i in range(len(options)):
                if i != my_idx and i not in votes:
                    votes.append(i)
                if len(votes) == 2:
                    break

        return {"votes": votes}

    # ---------------------------------------------------------
    # Função Auxiliar de Limpeza de Texto
    # ---------------------------------------------------------
    def _normalize_words(self, text: str) -> set[str]:
        # Remove stopwords básicas para não poluir o cálculo matemático
        stopwords = {"a", "o", "e", "de", "do", "da", "em", "um", "uma", "que", "para", "por", "com", "na", "no", "as", "os", "se", "eu", "me"}
        cleaned = []
        for token in text.lower().split():
            token = "".join(ch for ch in token if ch.isalnum())
            if token and token not in stopwords:
                cleaned.append(token)
        return set(cleaned)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("game_master_url")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--llm-url", default="http://127.0.0.1:9000")
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    agent = LLMAgent(name=args.name or f"LLMAgent_{args.port}", llm_url=args.llm_url)
    app.register(agent)
    app.run(host=args.host, port=args.port)

if __name__ == "__main__":
    main()