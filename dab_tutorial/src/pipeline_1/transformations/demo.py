import dlt

@dlt.table
def demo_table_dab():
    return spark.range(100)