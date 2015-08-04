#include "solution.h"
#include <string.h>
#include <ctype.h>

#define BUFFERSIZE 256

int palindrom(char* string)
{
    char forward[BUFFERSIZE], backward[BUFFERSIZE];
    int i = 0, j = 0;

    for (i = 0; i < strlen(string); i++)
    {
        if (isalnum(string[i]))
            forward[j++] = tolower(string[i]);
    }
    forward[j] = '\0';

    j = 0;
    for (i = strlen(string); i >= 0; i--)
    {
        if (isalnum(string[i]))
            backward[j++] = tolower(string[i]);
    }
    backward[j] = '\0';

    if (strcmp(forward, backward))
    {
        return 0;
    }
    else
    {
        return 1;
    }
}
