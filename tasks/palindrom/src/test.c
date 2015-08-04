#include <assert.h>
#include <string.h>
#include <CUnit/Basic.h>
#include <CUnit/Automated.h>
#include "solution.h"


static void test_real_palindroms(void)
{
    char string[256];
    strcpy(string, "Leben Sie mit im Eisnebel?");
    CU_ASSERT(palindrom(string) == 1);
    strcpy(string, "Die Liebe ist Sieger, rege ist sie bei Leid.");
    CU_ASSERT(palindrom(string) == 1);
    strcpy(string, "Bei Liese sei lieb!");
    CU_ASSERT(palindrom(string) == 1);
    strcpy(string, "Ella rüffelte Detlef für alle.");
    CU_ASSERT(palindrom(string) == 1);
    strcpy(string, "Renate bittet Tibetaner.");
    CU_ASSERT(palindrom(string) == 1);
    strcpy(string, "O Genie, der Herr ehre Dein Ego.");
    CU_ASSERT(palindrom(string) == 1);
    strcpy(string, "Ein Esel lese nie.");
    CU_ASSERT(palindrom(string) == 1);
    strcpy(string, "Leg in eine so helle Hose nie'n Igel.");
    CU_ASSERT(palindrom(string) == 1);
    strcpy(string, "An!Na!");
    CU_ASSERT(palindrom(string) == 1);
}


static void test_false_palindroms(void)
{
    char string[256];
    strcpy(string, "Test");
    CU_ASSERT(palindrom(string) == 0);
    strcpy(string, "No Palindrom!");
    CU_ASSERT(palindrom(string) == 0);
}


int main(void)
{
    CU_pSuite pSuite1 = NULL;
    
    if (CUE_SUCCESS != CU_initialize_registry())
    {
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    pSuite1 = CU_add_suite("Palindrom check", NULL, NULL);
    if (NULL == pSuite1)
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    if (NULL == CU_add_test(pSuite1, "Test string that are a palindrom", test_real_palindroms))
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    if (NULL == CU_add_test(pSuite1, "Test string that are not a palindrom", test_false_palindroms))
    {
        CU_cleanup_registry();
        fprintf(stderr, "%s", CU_get_error_msg());
        exit(-1);
    }
    
    CU_automated_run_tests();
    CU_cleanup_registry();
    
    return 0;
}
