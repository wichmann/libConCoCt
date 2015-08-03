#include <assert.h>
#include <CUnit/Basic.h>
#include <CUnit/Automated.h>
#include "solution.h"


static void test_leap_years(void)
{
    CU_ASSERT(leapyear(2000) == 1);
    CU_ASSERT(leapyear(2004) == 1);
    CU_ASSERT(leapyear(2012) == 1);
}


static void test_non_leap_years(void)
{
    CU_ASSERT(leapyear(1900) == 0);
    CU_ASSERT(leapyear(1901) == 0);
    CU_ASSERT(leapyear(2001) == 0);
}


int main(void)
{
    CU_pSuite pSuite1 = NULL;
    
    if (CUE_SUCCESS != CU_initialize_registry())
    {
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    pSuite1 = CU_add_suite("Leap year check", NULL, NULL);
    if (NULL == pSuite1)
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    if (NULL == CU_add_test(pSuite1, "Test correct leap years", test_leap_years))
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    if (NULL == CU_add_test(pSuite1, "Test non leap years", test_non_leap_years))
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }

    CU_automated_run_tests();
    CU_cleanup_registry();
    
    return 0;
}
