# Manuel testplan

Registrer dato, browser, valgt sprog, dokumentversion og korte observationer for hver kørsel. Brug hovedtelefoner for at undgå ekko.

## Forberedelse

1. Åbn appen i en Chromium-baseret browser og tillad mikrofonen.
2. Upload et kort dokument med mindst fem entydige fakta på både dansk og engelsk.
3. Vent på uploadstatus, og kontroller at eventloggen ikke viser fejl.
4. Start en ny Realtime-session for hver testgruppe.

## Testmatrix

| ID | Mode | Prompt | Forventet resultat |
|----|------|--------|--------------------|
| DA-1 | Dansk | Fortæl kort hvad du kan hjælpe med. | Naturlig dansk udtale og ordstilling; intet spontant skift til engelsk. |
| DA-2 | Dansk | Sig en sætning med tal, dato og dansk stednavn. | Forståelige tal, datoer og danske vokaler. |
| EN-1 | English | Briefly explain what you can help with. | Natural English response without Danish interference. |
| EN-2 | English | Say a sentence containing a number, a date, and a place name. | Clear number/date rendering and pronunciation. |
| AUTO-1 | Auto | Start på dansk, og fortsæt derefter på engelsk. | Modellen følger sproget uden at miste samtalekontekst. |
| AUTO-2 | Auto | Skift sprog midt i samme ytring. | Fornuftig håndtering uden lang pause eller forkert svar-sprog. |
| KB-DA | Dansk | Stil et spørgsmål, som kun det uploadede dokument kan besvare. | Korrekt grounded svar og mindst én synlig kilde. |
| KB-EN | English | Ask for a fact found only in the uploaded document. | Correct grounded answer and at least one visible source. |
| KB-MISS | Auto | Spørg om en oplysning, der ikke findes i dokumentet. | Modellen siger tydeligt, at kilden ikke indeholder svaret. |
| KB-UPDATE | Auto | Upload en ændret fil og spørg til den nye oplysning. | Det opdaterede indhold bliver søgbart efter indexering. |

## Vurdering

Giv hvert punkt 1-5 og noter konkrete eksempler:

- Sproggenkendelse
- Udtale og prosodi
- Svartid til første lyd
- Afbrydelse/barge-in
- Faktuel korrekthed
- Kilderelevans
- Håndtering af manglende viden

En kørsel består, når health endpoint svarer 200, alle fire kerneflows (DA, EN, Auto og knowledge) fungerer, og grounded svar ikke opfinder kilder.