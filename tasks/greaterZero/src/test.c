#include <assert.h>
#include <CUnit/Basic.h>
#include <CUnit/Automated.h>
#include "solution.h"


static void test_positive_numbers(void)
{
    CU_ASSERT(greater_than_zero(3) == 1);
    CU_ASSERT(greater_than_zero(42) == 1);
    CU_ASSERT(greater_than_zero(2000000000) == 1);
}


static void test_zero(void)
{
    CU_ASSERT(greater_than_zero(0) == 0);
}

static void test_negative_numbers(void)
{
    CU_ASSERT(greater_than_zero(-3) == 0);
    CU_ASSERT(greater_than_zero(-2000000000) == 0);
    CU_ASSERT(greater_than_zero(-1) == 0);
}


int main(void)
{
    CU_pSuite pSuite1 = NULL;
    
    if (CUE_SUCCESS != CU_initialize_registry())
    {
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    pSuite1 = CU_add_suite("Greater than Null", NULL, NULL);
    if (NULL == pSuite1)
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    if (NULL == CU_add_test(pSuite1, "Test positive numbers", test_positive_numbers))
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    if (NULL == CU_add_test(pSuite1, "Test zero", test_zero))
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    if (NULL == CU_add_test(pSuite1, "Test negative numbers", test_negative_numbers))
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }

    CU_automated_run_tests();
    CU_cleanup_registry();
    
    return 0;
}
