#include <stdlib.h>
#include <assert.h>
#include "solution.h"

int main()
{
    int number = 1;
    char string[10];
    
    while(number != 0) {
        printf("Enter number (0 to exit): ");
        scanf("%d", &number);
        fizzbuzz(number, string);
        printf("%s\n", string);
    }

    return 0;
}
