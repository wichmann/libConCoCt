#include <stdio.h>
#include <stdlib.h>
#include <CUnit/Basic.h>
#include <CUnit/Automated.h>
#include "lib.h"
#include <dirent.h> 


static void test1(void)
{
    CU_ASSERT(1);
    CU_ASSERT(0);
}


static void ls_path(char * path, int indent)
{
    char temp[100];
    DIR           *d;
    struct dirent *dir;
    
    d = opendir(path);
    if (d)
    {
        while ((dir = readdir(d)) != NULL)
        {
            if ((strcmp(dir->d_name, ".") != 0) && (strcmp(dir->d_name, "..") != 0))
            {
                for (int i = 0; i < indent; i++)
                {
                    printf("  ");
                }
                printf("%s\n", dir->d_name);
                strcpy(temp, path);
                strcat(temp, dir->d_name);
                ls_path(temp, indent + 2);
            }
        }
        closedir(d);
    }
}


int main(void)
{
    int x;

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

    ls_path("/", 0);

    return 0;
}





