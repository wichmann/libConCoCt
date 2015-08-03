#include <stdio.h>
#include "lib.h"
#include "interface.h"

int main(void)
{
    int temp = lib_func();
    int temp2 = student_func(temp);

    printf("%d\n", temp2);    

    return 0;
}
