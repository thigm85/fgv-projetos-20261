from scripts.01_provision_rds import main as provision_rds
from scripts.02_load_classicmodels import main as load_classicmodels
from scripts.03_validate_classicmodels import main as validate_classicmodels
from scripts.04_destroy_rds import main as destroy_rds

if __name__ == "__main__":
    provision_rds()
    load_classicmodels()
    validate_classicmodels()
    
    if input("Destroy RDS? (y/n): ").lower() == "y":
        destroy_rds()
    else:
        print("RDS maintained.")