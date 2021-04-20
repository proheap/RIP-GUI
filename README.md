
Implementácia smerovacieho protokolu RIP v jazyku Python  
[![Latest 1.0](https://img.shields.io/badge/latest-v1.0-red.svg)]()
[![Python 3.7](https://img.shields.io/badge/python-v3.7-green.svg)](https://www.python.org/downloads/release/python-393/) 
===

## Vedúci
*Ing. Martin Kontšek [KIS]*

## Cieľ
Interpretovací jazyk Python je aktuálne veľmi populárny v mnohých oblastiach, jednou z nich je sieťové programovanie, teda implementácia komunikačných protokolov. Cieľom záverečnej práce je implementácia vybraných funkcií smerovacieho protokolu RIP (Routing Information Protocol) v jazyku Python (backend) ako aj používateľsky prívetivého rozhrania pre nastavenie parametrov funkcií RIP (frontend).

## Obsah
* Rozbor dostupných RFC dokumentov, popisujúcich teoretické vlastnosti smerovacieho protokolu RIP
* Výber konkrétnych funkcií po vzájomnej dohode s vedúcim práce, ktorých implementácii sa študent bude venovať v praktickej časti.
* Návrh vhodných algoritmov a dátových štruktúr vychádzajúc z rozboru RFC dokumentov
* Implementácia zvolených funkcií RIP v jazyku Python (backend) v LinuxOS
* Vytvorenie používateľského rozhrania pre prívetivé ovládanie programu (frontend), napr. WebGUI bežiace na lokálnom webovom serveri.
* Testovanie - verifikácia a validácia výsledného programu:
    - použitie softvérových nástrojov vo virtualizovanom prostredí, napr. FRR, Cumulus Linux
    - nasadenie programu do siete v laboratóriach KIS a otestovanie jeho pripojením k reálnym sieťovým zariadeniam
