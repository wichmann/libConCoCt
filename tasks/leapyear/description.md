 
Schaltjahresüberprüfung
=======================
 
Beschreibung
------------
Es soll überprüft werden, ob ein gegebenes Jahr ein Schaltjahr ist oder nicht.
Die Bewertung erfolgt nach dem gregorianischen Kalender.

"Die Schaltjahrregel im Gregorianischen Kalender besteht aus drei Regeln, wobei die erste vom julianischen Kalender übernommen wurde:

 * Die durch 4 ganzzahlig teilbaren Jahre sind Schaltjahre. Die mittlere Länge eines Kalenderjahres erhöht sich dadurch um einen viertel Tag von 365 Tage auf 365,25 Tage.
 * Die durch 100 ganzzahlig teilbaren Jahre (z.B. 1700, 1800, 1900, 2100 und 2200) sind keine Schaltjahre. Im Durchschnitt verringert sich dadurch die Länge des Kalenderjahres um 0,01 Tage von 365,25 Tage auf 365,24 Tage.
 * Schließlich sind die ganzzahlig durch 400 teilbaren Jahre doch Schaltjahre. Damit sind 1600, 2000, 2400, ... jeweils wieder Schaltjahre. Die mittlere Länge des Kalenderjahres erhöht sich um 0,0025 Tage von 365,2400 Tage auf 365,2425 Tage."

[Quelle](https://de.wikipedia.org/wiki/Schaltjahr#Gregorianischer_Kalender)


Übergabeparameter
-----------------
jahreszahl: int 
    Jahr, das überprüft werden soll.


Rückgabewerte
-------------
1, wenn das Jahr ein Schaltjahr ist.
0, wenn das Jahr kein Schaltjahr ist.
