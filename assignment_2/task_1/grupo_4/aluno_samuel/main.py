from utils.tasks import (
    task_init_watermark,
    task_validate,
    task_simulate_orders
)


def main():

    print("Step 1/4")
    task_init_watermark()

    print("\nStep 2/4")
    task_validate()

    print("\nStep 3/4")
    task_simulate_orders()

    print("\nStep 4/4")
    task_validate()


if __name__ == "__main__":
    main()