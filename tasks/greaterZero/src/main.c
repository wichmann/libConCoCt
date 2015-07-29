#include <stdio.h>
#include <assert.h>
#include "solution.h"

int main(void)
{
    int ret = 0;
    
    ret = greater_than_zero(2);
    assert(ret == 1);
    
    ret = greater_than_zero(42);
    assert(ret == 1);
    
    ret = greater_than_zero(-17);
    assert(ret == 0);
    
    ret = greater_than_zero(0);
    assert(ret == 0);
    
    return 0;
}
