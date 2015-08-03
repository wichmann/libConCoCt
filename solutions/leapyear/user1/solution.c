#include "solution.h"

int leapyear(int year)
{
    if ((year & 3) == 0 && ((year % 25) != 0 || (year & 15) == 0))
    {
        return 1;
    }
    else
    {
        return 0;
    }
}
