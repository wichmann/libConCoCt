#include <stdlib.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "solution.h"

#define BUFFERSIZE 256

int main()
{
    char string[BUFFERSIZE] = " ";
    int result = 0;

    while(strlen(string) != 0) {
        printf("Enter string (<Enter> to exit): ");
        fgets(string, BUFFERSIZE, stdin);
        // remove newline at the end
        string[strlen(string) - 1] = 0;
        if (strlen(string) != 0)
        {
            result = palindrom(string);
            if (result)
            {
                printf("'%s' is a palindrom!\n", string);
            } else
            {
                printf("'%s' is not a palindrom!\n", string);
            }
        }
    }

    return 0;
}
