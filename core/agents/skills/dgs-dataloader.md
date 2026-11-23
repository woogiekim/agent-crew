# Skill: dgs-dataloader

## Source
- Netflix DGS Framework, "Data Loaders (N+1)"
- GraphQL Java, "Batching"
- graphql-java/java-dataloader, project README

## When to Apply
- Before changing DGS list or nested field resolvers that load related data
- Before a resolver calls Feign, REST, gRPC, or a repository per parent
- For ID-based enrichment of products, orders, shops, options, prices, inventory, reviews, or promotions
- When a downstream service exposes or needs a batch endpoint such as `findByIds(ids)`
- In reviews of queries that can trigger a remote or DB call per parent row

## Core Rules

### Rule 1: Batch nested resolver dependencies
> Source: Netflix DGS Data Loaders (N+1), "Implementing a Data Loader"

Batch keyed nested fields with a DGS DataLoader. Keep per-parent calls to
Feign, repositories, and services out of field resolvers.

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

Call a batch-capable dependency. For Feign clients limited to `getById(id)`,
add or request a bulk endpoint such as `getByIds(ids)` before claiming batching.

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

Use `MappedBatchLoader<K, V>` for missing keys or uncertain response order.
With `BatchLoader<K, V>`, return values in exact input-key order.

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

Keep `DataLoader` instances out of singleton fields and global objects.
Scope the cache to the request. Any explicitly designed shared cache must
key on user, tenant, locale, and authorization.

```kotlin
// BAD: singleton field can leak cached data across users.
private lateinit var shopsLoader: DataLoader<Long, Shop>

// GOOD: resolve the request's loader from the environment.
val shopsLoader = dfe.getDataLoader<Long, Shop>("shopsById")
```

### Rule 5: Keep asynchronous work inside the batch loader
> Source: GraphQL Java Batching, "Async Calls On Your Batch Loader Function Only"

Call `DataLoader.load` synchronously during field resolution. Run asynchronous
I/O inside the batch loader.

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

In a unit or integration test, query multiple parents and verify one bulk call
with all expected IDs. For Feign, mock the bulk method and verify the aggregated request.

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
