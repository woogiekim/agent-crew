# Skill: dgs-dataloader

## Source
- Netflix DGS Framework, "Data Loaders (N+1)"
- GraphQL Java, "Batching"
- graphql-java/java-dataloader, project README

## When to Apply
- Before changing a DGS GraphQL field resolver that loads related data for a list field or nested object field
- Before calling a Feign, REST, gRPC, or repository dependency from a resolver for each parent object
- When a resolver enriches products, orders, shops, options, prices, inventory, reviews, or promotions by ID
- When downstream services expose or need a batch endpoint such as `findByIds(ids)`
- During review when a GraphQL query can return many parent rows and each row triggers another remote or database call

## Core Rules

### Rule 1: Batch nested resolver dependencies
> Source: Netflix DGS Data Loaders (N+1), "Implementing a Data Loader"

Use a DGS DataLoader for nested fields that resolve related records by key.
Do not call a Feign client, repository, or service once per parent object from
the field resolver.

```kotlin
// BAD: N parents produce N downstream calls.
@DgsData(parentType = "Product", field = "shop")
fun shop(dfe: DgsDataFetchingEnvironment): Shop {
    val product = dfe.getSource<Product>()

    return shopClient.getShop(product.shopId)
}

// GOOD: every parent schedules one key and DGS dispatches a batch.
@DgsData(parentType = "Product", field = "shop")
fun shop(dfe: DgsDataFetchingEnvironment): CompletableFuture<Shop?> {
    val product = dfe.getSource<Product>()
    val loader = dfe.getDataLoader<Long, Shop>("shopsById")

    return loader.load(product.shopId)
}
```

### Rule 2: Require a real batch boundary
> Source: Netflix DGS Data Loaders (N+1), "What If My Service Doesn't Support Loading in Batches?"

The loader must call a batch-capable dependency. If a Feign client only exposes
`getById(id)`, add or request a bulk endpoint such as `getByIds(ids)` before
claiming the resolver is batched.

```kotlin
// BAD: hides N calls inside the loader.
override fun load(keys: List<Long>): CompletionStage<List<Shop?>> =
    CompletableFuture.supplyAsync { keys.map { shopClient.getShop(it) } }

// GOOD: one remote call for the collected keys.
override fun load(keys: List<Long>): CompletionStage<List<Shop?>> =
    CompletableFuture.supplyAsync { shopClient.getShops(keys) }
```

### Rule 3: Preserve key-to-value mapping explicitly
> Source: Netflix DGS Data Loaders (N+1), "MappedBatchLoader"

Use `MappedBatchLoader<K, V>` when some keys may be missing or when the
downstream response order is not guaranteed. For `BatchLoader<K, V>`, return
values in exactly the same order as the incoming keys.

```kotlin
@DgsDataLoader(name = "shopsById")
class ShopsByIdLoader(
    private val shopClient: ShopClient
) : MappedBatchLoader<Long, Shop> {
    override fun load(keys: Set<Long>): CompletionStage<Map<Long, Shop>> =
        CompletableFuture.supplyAsync {
            shopClient.getShops(keys.toList()).associateBy { it.id }
        }
}
```

### Rule 4: Keep DataLoader caches request-scoped
> Source: GraphQL Java Batching, "Per Request Data Loaders"

Do not store `DataLoader` instances in singleton service fields or global
objects. Treat the loader cache as request-scoped unless a shared cache is
explicitly designed with user, tenant, locale, and authorization in the cache
key.

```kotlin
// BAD: singleton field can leak cached data across users.
private lateinit var shopsLoader: DataLoader<Long, Shop>

// GOOD: resolve the request's loader from the environment.
val shopsLoader = dfe.getDataLoader<Long, Shop>("shopsById")
```

### Rule 5: Keep asynchronous work inside the batch loader
> Source: GraphQL Java Batching, "Async Calls On Your Batch Loader Function Only"

Do not call `DataLoader.load` from a delayed off-thread block inside the data
fetcher. Schedule the load synchronously in the resolver and put asynchronous
I/O inside the loader implementation.

```kotlin
// BAD: the GraphQL engine may not see this delayed load in time to dispatch it.
return CompletableFuture.supplyAsync {
    dfe.getDataLoader<Long, Shop>("shopsById").load(product.shopId)
}

// GOOD: load is scheduled during field resolution.
return dfe.getDataLoader<Long, Shop>("shopsById").load(product.shopId)
```

### Rule 6: Verify batching with a measurable call-count test
> Source: graphql-java/java-dataloader README, statistics and batching behavior

Add a unit or integration test that executes a query returning multiple parents
and asserts the downstream batch dependency is called once with all expected
IDs. For Feign clients, mock the bulk method and verify the single aggregated
request.

```kotlin
verify(exactly = 1) { shopClient.getShops(match { it.containsAll(shopIds) }) }
verify(exactly = 0) { shopClient.getShop(any()) }
```

## Anti-Patterns
- Calling Feign or REST `getById` from a DGS field resolver for every parent row
- Wrapping per-key remote calls inside a `BatchLoader` and calling it "batched"
- Using a singleton `DataLoader` or global cache without user and tenant isolation
- Returning `BatchLoader` values in downstream response order instead of input-key order
- Adding DataLoader after implementation without a call-count test that catches N+1 regressions

## Interaction with Other Skills
- Use `database-design.md` when the batch dependency reads from SQL or an ORM repository.
- Use `api-design.md` when a missing downstream bulk endpoint requires a new API contract.
- Use `effective-kotlin.md` for coroutine, nullability, and collection handling in Kotlin loaders.
- Use `tdd.md` to write the failing call-count test before replacing resolver logic.

## References
- Netflix DGS Framework, "Data Loaders (N+1)", https://netflix.github.io/dgs/data-loaders/
- GraphQL Java, "Batching", https://graphql-java.com/documentation/master/batching/
- graphql-java/java-dataloader README, https://github.com/graphql-java/java-dataloader
