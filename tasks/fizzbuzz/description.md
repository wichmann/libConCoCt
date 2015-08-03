 
FizzBuzz
========
 
Beschreibung
------------
Es soll in Abhängigkeit von einer übergebenen Zahl ein String zusammengesetzt
werden. Ist die Zahl ohne Rest durch 3 teilbar, wird das Wort "Fizz" in den
String geschrieben, ist die Zahl ohne Rest durch 5 teilbar wird das Wort "Buzz"
angehängt. Sollte die Zahl weder durch 3 noch durch 5 teilbar sein, enthält der
String die Zahl.

[Quelle](https://en.wikipedia.org/wiki/Fizz_buzz)


Übergabeparameter
-----------------
zahl: int 
    Zahl, die überprüft werden soll.
string: char[]
    String, in den die Lösung hineingeschrieben werden soll.


Rückgabewerte
-------------
"Fizz", wenn die Zahl durch 3 teilbar ist.
"Buzz", wenn die Zahl durch 5 teilbar ist.
"Fizz Buzz", wenn die Zahl sowohl durch 3 als auch durch 5 teilbar ist.
String mit der übergebenen Zahl, in allen anderen Fällen.
