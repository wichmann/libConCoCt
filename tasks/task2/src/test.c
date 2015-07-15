#include <assert.h>
#include <CUnit/Basic.h>
#include <CUnit/Automated.h>
#include "lib.h"
#include "interface.h"


static void test1(void)
{
    CU_ASSERT(1);
    CU_ASSERT(0);
}


int main(void)
{
    CU_pSuite pSuite1 = NULL;
    
    if (CUE_SUCCESS != CU_initialize_registry())
    {
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    pSuite1 = CU_add_suite("Suite_1", NULL, NULL);
    if (NULL == pSuite1)
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    if (NULL == CU_add_test(pSuite1, "some test", test1))
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }

    /* TODO: set output file */

    CU_automated_run_tests();
    CU_cleanup_registry();
    
    return 0;
}
