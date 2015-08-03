#include "solution.h"
#include <string.h>
#include <stdio.h>

void fizzbuzz(int number, char* string)
{
    if (number % 15 == 0)
    {
        sprintf(string, "Fizz Buzz");
    }
    else if (number % 3 == 0)
    {
        sprintf(string, "Fizz");
    }
    else if (number % 5 == 0)
    {
        sprintf(string, "Buzz");
    }
    else
    {
        sprintf(string, "%i", number);
    }
}
