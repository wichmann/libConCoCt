 
Palindrom
=========
 
Beschreibung
------------
Palindrome sind Texte, die von links nach rechts genau so gelesen werden können, wie von rechts nach links. Bei der Überprüfung sollen Leerzeichen, Tabs, Sonderzeichen und Groß- und Klein­schreibung vernachlässigt werden.

Beispiele: 

    Leben Sie mit im Eisnebel? 
    Die Liebe ist Sieger, rege ist sie bei Leid. 
    Bei Liese sei lieb! 
    Ella rüffelte Detlef für alle. 
    Renate bittet Tibetaner. 
    O Genie, der Herr ehre Dein Ego. 
    Ein Esel lese nie. 
    Leg in eine so helle Hose nie'n Igel. 

Schreiben Sie ein Programm, welches

1. einen Text einliest, 
2. den eingelesenen Text wieder ausgibt, 
3. die Länge des Textes ermittelt, 
4. den Text in umgekehrter Reihenfolge ausgibt, 
5. und entscheidet, ob dieser Text ein Palindrom ist oder nicht. 

Der Text soll maximal 255 Zeichen enthalten. Leerzeichen sowie Groß- und Kleinschreibung sollen erlaubt sein. Verwenden Sie dazu Funktionen aus der string- und der ctype-Bibliothek:

    <ctype.h>
    int isalnum(int c);
    int isalpha(int c);
    int isdigit(int c);
    int islower(int c);
    int ispunct(int c);
    int isspace(int c);
    int isupper(int c);
    int tolower(int c);
    int toupper(int c);

    <string.h>
    char* strcpy(char* s, const char* ct);
    char* strncpy(char* s, const char* ct, size_t n);
    int strcmp(const char* cs, const char* ct);
    int strncmp(const char* cs, const char* ct, size_t n);
    size_t strlen(const char* cs);

[Quelle](https://de.wikipedia.org/wiki/Palindrom)


Übergabeparameter
-----------------
string: char[]
    String, der auf ein Palindrom überprüft werden soll


Rückgabewerte
-------------
1, wenn der übergebene String ein Palindrom enthält
0, wenn der übergebene String kein Palindrom enthält
