#include <assert.h>
#include <string.h>
#include <CUnit/Basic.h>
#include <CUnit/Automated.h>
#include "solution.h"


static void test_numbers(void)
{
    char string[10];
    fizzbuzz(1, string);
    CU_ASSERT(strcmp(string, "1") == 0);
    fizzbuzz(2, string);
    CU_ASSERT(strcmp(string, "2") == 0);
    fizzbuzz(4, string);
    CU_ASSERT(strcmp(string, "4") == 0);
}


static void test_fizz(void)
{
    char string[10];
    fizzbuzz(3, string);
    CU_ASSERT(strcmp(string, "Fizz") == 0);
    fizzbuzz(6, string);
    CU_ASSERT(strcmp(string, "Fizz") == 0);
    fizzbuzz(9, string);
    CU_ASSERT(strcmp(string, "Fizz") == 0);
}


static void test_buzz(void)
{
    char string[10];
    fizzbuzz(5, string);
    CU_ASSERT(strcmp(string, "Buzz") == 0);
    fizzbuzz(10, string);
    CU_ASSERT(strcmp(string, "Buzz") == 0);
    fizzbuzz(20, string);
    CU_ASSERT(strcmp(string, "Buzz") == 0);
}


static void test_fizzbuzz(void)
{
    char string[10];
    fizzbuzz(15, string);
    CU_ASSERT(strcmp(string, "Fizz Buzz") == 0);
    fizzbuzz(30, string);
    CU_ASSERT(strcmp(string, "Fizz Buzz") == 0);
    fizzbuzz(45, string);
    CU_ASSERT(strcmp(string, "Fizz Buzz") == 0);
}


int main(void)
{
    CU_pSuite pSuite1 = NULL;
    
    if (CUE_SUCCESS != CU_initialize_registry())
    {
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    pSuite1 = CU_add_suite("FizzBuzz check", NULL, NULL);
    if (NULL == pSuite1)
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    if (NULL == CU_add_test(pSuite1, "Test non divideable numbers", test_numbers))
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    if (NULL == CU_add_test(pSuite1, "Test numbers divideable by 3", test_fizz))
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }

    if (NULL == CU_add_test(pSuite1, "Test numbers divideable by 5", test_buzz))
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    if (NULL == CU_add_test(pSuite1, "Test numbers divideable by 3 and 5", test_fizzbuzz))
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    CU_automated_run_tests();
    CU_cleanup_registry();
    
    return 0;
}
