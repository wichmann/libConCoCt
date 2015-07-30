#include <stdlib.h>
#include <assert.h>
#include "solution.h"

int main()
{
    int ret = 0, year = 0;
    
    printf("Enter year: ");
    scanf("%d", &year);
    
    ret = leapyear(year);
    
    if (ret)
    {
        printf("Leap year!");
    }
    else
    {
        printf("Not a leap year!");
    }

    return 0;
}
