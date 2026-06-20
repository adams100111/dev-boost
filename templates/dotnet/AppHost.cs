// templates/dotnet — illustrative .NET Aspire AppHost (Program.cs of the *.AppHost project).
//
// Shared infra (Postgres + Redis) is declared with PERSISTENT containers and a data
// volume so local data survives `dotnet run` restarts of the AppHost — you do not lose
// your database between debug sessions. This is the dev-boost convention for the
// .NET stack (see templates/dotnet/README.md).
//
// Generate a fresh solution with `aspire new` and adapt this AppHost to taste.

var builder = DistributedApplication.CreateBuilder(args);

// PostgreSQL — persistent container + named data volume (data survives restarts).
var postgres = builder.AddPostgres("postgres")
    .WithDataVolume()
    .WithLifetime(ContainerLifetime.Persistent);

var appdb = postgres.AddDatabase("appdb");

// Redis cache — persistent container + data volume.
var cache = builder.AddRedis("cache")
    .WithDataVolume()
    .WithLifetime(ContainerLifetime.Persistent);

// Your service projects wire the shared infra via references, e.g.:
//
// builder.AddProject<Projects.Api>("api")
//     .WithReference(appdb)
//     .WithReference(cache)
//     .WaitFor(appdb);

builder.Build().Run();
